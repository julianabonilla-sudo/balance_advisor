"""Advisory engine — generates buy/sell recommendations from coverage data.

Business rules:
  - Mercado regulado  : COMPRA only (cannot sell in regulated market)
  - Mercado no regulado: COMPRA and VENTA allowed

Price logic:
  - Suggested BUY price  : below min observed bolsa price  → always beats bolsa
  - Suggested SELL price : above avg weighted NR buy price → guaranteed margin
"""

from dataclasses import dataclass, field
from datetime import date

BUY_THRESHOLD_PCT  = 80.0   # below this → recommend buying
SELL_THRESHOLD_PCT = 100.0  # above this → recommend selling (NR only)


@dataclass
class MarketRec:
    market: str               # "regulado" | "no_regulado"
    action: str               # "COMPRA" | "VENTA"
    coverage_pct: float
    gap_gwh: float            # positive = volume to buy or sell
    suggested_price_cop_kwh: float   # target price ceiling (buy) or floor (sell)
    bolsa_price_cop_kwh: float
    price_reference_cop_kwh: float   # min bolsa (buy) or avg NR buy (sell)

    @property
    def price_advantage_cop_kwh(self) -> float:
        """Advantage vs reference price: savings for buy, margin for sell."""
        return abs(self.bolsa_price_cop_kwh - self.suggested_price_cop_kwh)


@dataclass
class MonthAdvisory:
    year: int
    month: int
    label: str                    # "2027-03"
    coverage_reg_pct: float
    coverage_nr_pct: float
    balance_gwh: float
    recs: list[MarketRec] = field(default_factory=list)

    @property
    def buy_recs(self) -> list[MarketRec]:
        return [r for r in self.recs if r.action == "COMPRA"]

    @property
    def sell_recs(self) -> list[MarketRec]:
        return [r for r in self.recs if r.action == "VENTA"]


@dataclass
class AdvisoryReport:
    year: int
    month: int
    version_name: str
    bolsa_price: float          # current bolsa price (avg)
    min_bolsa_price: float      # minimum bolsa price observed → ceiling for buy contracts
    avg_nr_buy_price: float     # weighted avg buy price of NR portfolio → floor for sell
    coverage_rows: list[dict]   # 12-month coverage for chart section
    advisories: list[MonthAdvisory]

    @property
    def months_needing_buy(self) -> list[MonthAdvisory]:
        return [a for a in self.advisories if a.buy_recs]

    @property
    def months_needing_sell(self) -> list[MonthAdvisory]:
        return [a for a in self.advisories if a.sell_recs]


def build_advisory(
    year: int,
    month: int,
    version_name: str,
    bolsa_price: float,
    min_bolsa_price: float,      # min observed bolsa price → buy ceiling
    avg_nr_buy_price: float,     # weighted avg NR portfolio price → sell floor
    future_months_data: list[dict],
    coverage_rows: list[dict],
) -> AdvisoryReport:

    advisories: list[MonthAdvisory] = []

    for m in future_months_data:
        y, mo = m["year"], m["month"]
        lbl = f"{y}-{mo:02d}"

        demand_reg    = m.get("demand_reg_mwh", 0)
        contracts_reg = m.get("contracts_reg_mwh", 0)
        demand_nr     = m.get("demand_nr_mwh", 0)
        contracts_nr  = m.get("contracts_nr_mwh", 0)
        balance_mwh   = m.get("balance_mwh", 0)

        cov_reg = (contracts_reg / demand_reg * 100) if demand_reg > 0 else 0.0
        cov_nr  = (contracts_nr  / demand_nr  * 100) if demand_nr  > 0 else 0.0

        recs: list[MarketRec] = []

        # ── Regulado — COMPRA only (cannot sell in regulated market) ──────────
        if demand_reg > 0:
            gap_reg = (demand_reg - contracts_reg) / 1_000  # GWh, positive = short
            if cov_reg < BUY_THRESHOLD_PCT and gap_reg > 0:
                recs.append(MarketRec(
                    market="regulado", action="COMPRA",
                    coverage_pct=cov_reg, gap_gwh=gap_reg,
                    suggested_price_cop_kwh=min_bolsa_price,
                    bolsa_price_cop_kwh=bolsa_price,
                    price_reference_cop_kwh=min_bolsa_price,
                ))

        # ── No regulado — COMPRA and VENTA allowed ────────────────────────────
        if demand_nr > 0:
            gap_nr = (demand_nr - contracts_nr) / 1_000  # positive = short
            if cov_nr < BUY_THRESHOLD_PCT and gap_nr > 0:
                recs.append(MarketRec(
                    market="no_regulado", action="COMPRA",
                    coverage_pct=cov_nr, gap_gwh=gap_nr,
                    suggested_price_cop_kwh=min_bolsa_price,
                    bolsa_price_cop_kwh=bolsa_price,
                    price_reference_cop_kwh=min_bolsa_price,
                ))
            elif cov_nr > SELL_THRESHOLD_PCT and gap_nr < 0:
                recs.append(MarketRec(
                    market="no_regulado", action="VENTA",
                    coverage_pct=cov_nr, gap_gwh=abs(gap_nr),
                    suggested_price_cop_kwh=avg_nr_buy_price,
                    bolsa_price_cop_kwh=bolsa_price,
                    price_reference_cop_kwh=avg_nr_buy_price,
                ))

        advisories.append(MonthAdvisory(
            year=y, month=mo, label=lbl,
            coverage_reg_pct=cov_reg,
            coverage_nr_pct=cov_nr,
            balance_gwh=balance_mwh / 1_000,
            recs=recs,
        ))

    return AdvisoryReport(
        year=year, month=month, version_name=version_name,
        bolsa_price=bolsa_price,
        min_bolsa_price=min_bolsa_price,
        avg_nr_buy_price=avg_nr_buy_price,
        coverage_rows=coverage_rows,
        advisories=advisories,
    )
