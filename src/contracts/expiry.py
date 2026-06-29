"""Contract expiry analysis — identifies which buy contracts expire each month
and quantifies the coverage gap they leave behind.

Data flow:
  list_contracts()   → start_date / end_date / sic_code / market / operation
  balance.analysis() → scatter_contracts  → monthly qty (kWh) per sic_code
  Join by sic_code   → ExpiryEvent with volume and financial impact
"""

from dataclasses import dataclass, field
from datetime import date, datetime


# ──────────────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ExpiryEvent:
    sic_code: str
    contract_number: str
    contraparte: str
    market_type: str            # REGULADO | NO REGULADO
    contract_mode: str          # PLC | PLD | PLG
    start_date: date
    end_date: date
    monthly_qty_kwh: float      # avg kWh/month from most-recent balance analysis
    price_cop_kwh: float        # IPP-indexed price
    monthly_cost_cop: float     # monthly_qty_kwh × price_cop_kwh
    is_active_now: bool         # True if still delivering in the reference month


@dataclass
class ExpiryMonth:
    year: int
    month: int
    label: str                  # e.g. "2027-01"
    events: list[ExpiryEvent] = field(default_factory=list)

    @property
    def total_kwh_lost(self) -> float:
        return sum(e.monthly_qty_kwh for e in self.events)

    @property
    def total_cost_lost_cop(self) -> float:
        return sum(e.monthly_cost_cop for e in self.events)

    @property
    def regulado_kwh_lost(self) -> float:
        return sum(e.monthly_qty_kwh for e in self.events if "REGULADO" in e.market_type and "NO" not in e.market_type)

    @property
    def no_regulado_kwh_lost(self) -> float:
        return sum(e.monthly_qty_kwh for e in self.events if "NO" in e.market_type)


@dataclass
class ExpiryCalendar:
    reference_year: int
    reference_month: int
    horizon_months: int
    months: list[ExpiryMonth]           # sorted chronologically, non-empty only
    all_events: list[ExpiryEvent]

    def months_with_expiry(self) -> list[ExpiryMonth]:
        return [m for m in self.months if m.events]

    def largest_cliff(self) -> ExpiryMonth | None:
        candidates = self.months_with_expiry()
        if not candidates:
            return None
        return max(candidates, key=lambda m: m.total_kwh_lost)


# ──────────────────────────────────────────────────────────────────────────────
# Builder
# ──────────────────────────────────────────────────────────────────────────────

def _parse_date(s: str) -> date:
    return datetime.fromisoformat(s.replace("Z", "")).date()


def build_expiry_calendar(
    contracts_list: dict,
    scatter_contracts: list[dict],
    reference_year: int,
    reference_month: int,
    horizon_months: int = 18,
) -> ExpiryCalendar:
    """Build an expiry calendar for the next `horizon_months` months.

    Args:
        contracts_list:    raw response from contracts.list() — has ``items`` key
        scatter_contracts: list from balance.analysis() → scatter_contracts
        reference_year / reference_month: the "today" anchor month
        horizon_months: how many future months to scan
    """
    ref = date(reference_year, reference_month, 1)

    # Build a lookup: sic_code → {qty_kwh, price, total}
    volume_by_sic: dict[str, dict] = {
        str(sc["name"]): sc
        for sc in scatter_contracts
        if sc.get("qty", 0) > 0
    }

    # Parse all buy contracts
    items = contracts_list.get("items", [])
    buy_contracts = [c for c in items if c.get("operation_type") == "COMPRA"]

    # Determine the horizon window
    horizon_end_year = reference_year + (reference_month + horizon_months - 1) // 12
    horizon_end_month = (reference_month + horizon_months - 1) % 12 + 1

    # Build ExpiryEvent for each contract that expires within the horizon
    events: list[ExpiryEvent] = []
    for c in buy_contracts:
        end_d = _parse_date(c["end_date"])
        start_d = _parse_date(c["start_date"])

        # Only consider contracts expiring after the reference month and within horizon
        if (end_d.year, end_d.month) <= (reference_year, reference_month):
            continue
        if (end_d.year, end_d.month) > (horizon_end_year, horizon_end_month):
            continue

        sic = str(c.get("sic_code", ""))
        sc = volume_by_sic.get(sic, {})
        qty_kwh = sc.get("qty", 0.0)
        price = sc.get("price", 0.0)

        is_active = (start_d.year, start_d.month) <= (reference_year, reference_month) and \
                    (end_d.year, end_d.month) >= (reference_year, reference_month)

        events.append(ExpiryEvent(
            sic_code=sic,
            contract_number=c.get("contract_number", ""),
            contraparte=c.get("contraparte", ""),
            market_type=c.get("market_type", ""),
            contract_mode=c.get("contract_mode", ""),
            start_date=start_d,
            end_date=end_d,
            monthly_qty_kwh=qty_kwh,
            price_cop_kwh=price,
            monthly_cost_cop=qty_kwh * price,
            is_active_now=is_active,
        ))

    # Group events by their expiry month (the month after the contract ends
    # is when the gap appears)
    month_map: dict[tuple, ExpiryMonth] = {}
    for ev in events:
        # The GAP appears in the month AFTER expiry
        gap_y = ev.end_date.year if ev.end_date.month < 12 else ev.end_date.year + 1
        gap_m = ev.end_date.month + 1 if ev.end_date.month < 12 else 1
        key = (gap_y, gap_m)
        if key not in month_map:
            month_map[key] = ExpiryMonth(year=gap_y, month=gap_m, label=f"{gap_y}-{gap_m:02d}")
        month_map[key].events.append(ev)

    months_sorted = sorted(month_map.values(), key=lambda m: (m.year, m.month))

    return ExpiryCalendar(
        reference_year=reference_year,
        reference_month=reference_month,
        horizon_months=horizon_months,
        months=months_sorted,
        all_events=events,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Formatting helper for the agent
# ──────────────────────────────────────────────────────────────────────────────

def expiry_calendar_to_dict(cal: ExpiryCalendar) -> dict:
    months_with_expiry = cal.months_with_expiry()
    cliff = cal.largest_cliff()

    return {
        "reference_period": f"{cal.reference_year}-{cal.reference_month:02d}",
        "horizon_months": cal.horizon_months,
        "total_contracts_expiring": len(cal.all_events),
        "months_with_expiry": len(months_with_expiry),
        "largest_cliff": {
            "period": cliff.label if cliff else None,
            "total_mwh_lost": round(cliff.total_kwh_lost / 1000, 1) if cliff else 0,
            "total_cost_lost_mcop": round(cliff.total_cost_lost_cop / 1e6, 1) if cliff else 0,
        },
        "expiry_months": [
            {
                "period": m.label,
                "total_mwh_lost": round(m.total_kwh_lost / 1000, 1),
                "total_cost_lost_mcop": round(m.total_cost_lost_cop / 1e6, 1),
                "regulado_mwh_lost": round(m.regulado_kwh_lost / 1000, 1),
                "no_regulado_mwh_lost": round(m.no_regulado_kwh_lost / 1000, 1),
                "contracts": [
                    {
                        "sic_code": ev.sic_code,
                        "contract_number": ev.contract_number,
                        "contraparte": ev.contraparte,
                        "market": ev.market_type,
                        "mode": ev.contract_mode,
                        "period": f"{ev.start_date.strftime('%Y-%m')} → {ev.end_date.strftime('%Y-%m')}",
                        "monthly_mwh": round(ev.monthly_qty_kwh / 1000, 1),
                        "price_cop_kwh": round(ev.price_cop_kwh, 1),
                        "monthly_cost_mcop": round(ev.monthly_cost_cop / 1e6, 1),
                        "is_active_now": ev.is_active_now,
                    }
                    for ev in sorted(m.events, key=lambda e: e.monthly_qty_kwh, reverse=True)
                ],
            }
            for m in months_with_expiry
        ],
    }
