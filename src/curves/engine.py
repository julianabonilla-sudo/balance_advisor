"""Buy/sell curve engine and price-limit calculator for the Colombian electricity market."""

from dataclasses import dataclass, field
from enum import Enum


class MarketType(str, Enum):
    REGULADO = "regulado"
    NO_REGULADO = "no_regulado"
    TOTAL = "total"


class CurveDirection(str, Enum):
    BUY = "compra"
    SELL = "venta"


@dataclass
class CurvePoint:
    """One step in a buy or sell staircase curve."""
    contract_name: str
    market: str
    contract_type: str          # PLC, PLD, PLG, etc.
    price_cop_kwh: float
    qty_kwh: float
    cumulative_qty_kwh: float
    total_cop: float


@dataclass
class PriceLimitResult:
    market: str
    # Client sell prices
    sell_demand_price: float    # what clients pay for demand
    sell_bolsa_price: float     # what we get when selling surplus in bolsa
    sell_avg_price: float       # blended avg for the whole market
    # Buy prices
    buy_contract_price: float   # weighted avg of buy contracts
    bolsa_buy_price: float      # actual bolsa buy price this month
    # Limit
    price_limit: float          # max acceptable bolsa buy price
    margin_pct: float           # margin applied (default 0 = breakeven)
    # Gap
    gap_cop_kwh: float          # bolsa_buy_price - price_limit (positive = overpaying)
    is_above_limit: bool        # True when overpaying
    # Volume at risk
    bolsa_buy_kwh: float        # kWh bought in bolsa this month
    loss_cop: float             # gap × bolsa_buy_kwh (negative = financial loss)
    recommendation: str


@dataclass
class SensitivityPoint:
    price_scenario_cop_kwh: float
    additional_cost_cop: float      # vs current price
    total_bolsa_cost_cop: float
    is_above_limit: bool


@dataclass
class OptimizationResult:
    year: int
    month: int
    version_name: str
    # Overall position
    overall_balance_mwh: float
    is_long: bool               # True = long (surplus), False = short (must buy)
    # Curves
    buy_curve: list[CurvePoint]     # contracts sorted cheapest → most expensive
    sell_curve: list[CurvePoint]    # contracts sorted highest price → lowest
    # Limit analysis per market
    regulado: PriceLimitResult
    no_regulado: PriceLimitResult
    # Global
    global_price_limit: float       # min of both markets (most restrictive)
    total_bolsa_buy_kwh: float
    total_bolsa_buy_cop: float
    total_loss_above_limit_cop: float
    # Sensitivity
    sensitivity: list[SensitivityPoint]
    # Actionable output
    actions: list[str]


# ──────────────────────────────────────────────────────────────────────────────
# Core calculations
# ──────────────────────────────────────────────────────────────────────────────

def _build_buy_curve(scatter_contracts: list[dict]) -> list[CurvePoint]:
    """Build a merit-order buy curve: contracts sorted cheapest to most expensive."""
    with_qty = [c for c in scatter_contracts if c.get("qty", 0) > 0]
    sorted_contracts = sorted(with_qty, key=lambda c: c.get("price", 0))

    points: list[CurvePoint] = []
    cumulative = 0.0
    for c in sorted_contracts:
        qty = c.get("qty", 0)
        price = c.get("price", 0.0)
        cumulative += qty
        points.append(CurvePoint(
            contract_name=c.get("name", ""),
            market=c.get("market", ""),
            contract_type=c.get("type", ""),
            price_cop_kwh=price,
            qty_kwh=qty,
            cumulative_qty_kwh=cumulative,
            total_cop=qty * price,
        ))
    return points


def _build_sell_curve(income_sections: list[dict]) -> list[CurvePoint]:
    """Build a sell curve from income statement venta side, highest price first."""
    venta = next((s for s in income_sections if s.get("id") == "venta"), None)
    if not venta:
        return []

    items: list[dict] = []
    for sub in venta.get("sub_items", []):
        market_label = sub.get("label", "")
        for item in sub.get("items", []):
            items.append({
                "name": item.get("agente", ""),
                "market": market_label,
                "type": "",
                "price": item.get("precio_prom_cop", 0.0),
                "qty": item.get("cantidad_kwh", 0.0),
                "total": item.get("total_cop", 0.0),
            })

    sorted_items = sorted(
        [i for i in items if i["qty"] > 0],
        key=lambda i: i["price"],
        reverse=True,
    )

    points: list[CurvePoint] = []
    cumulative = 0.0
    for item in sorted_items:
        qty = item["qty"]
        cumulative += qty
        points.append(CurvePoint(
            contract_name=item["name"],
            market=item["market"],
            contract_type=item["type"],
            price_cop_kwh=item["price"],
            qty_kwh=qty,
            cumulative_qty_kwh=cumulative,
            total_cop=item["total"],
        ))
    return points


def _extract_market_prices(income_sections: list[dict]) -> dict:
    """Extract avg sell price for demand and bolsa per market from income statement."""
    prices = {
        "regulado": {"demand_price": 0.0, "bolsa_sell_price": 0.0, "demand_qty": 0.0, "bolsa_qty": 0.0},
        "no_regulado": {"demand_price": 0.0, "bolsa_sell_price": 0.0, "demand_qty": 0.0, "bolsa_qty": 0.0},
    }

    venta = next((s for s in income_sections if s.get("id") == "venta"), None)
    if not venta:
        return prices

    for sub in venta.get("sub_items", []):
        label = sub.get("label", "").lower()
        key = "regulado" if "regulado" in label and "no" not in label else "no_regulado"

        for item in sub.get("items", []):
            name = item.get("agente", "").lower()
            qty = item.get("cantidad_kwh", 0.0)
            price = item.get("precio_prom_cop", 0.0)
            if "demanda" in name or "demand" in name:
                prices[key]["demand_price"] = price
                prices[key]["demand_qty"] = qty
            elif "bolsa" in name:
                prices[key]["bolsa_sell_price"] = price
                prices[key]["bolsa_qty"] = qty

    return prices


def _calc_price_limit_for_market(
    market_key: str,
    market_label: str,
    demand_sell_price: float,
    bolsa_sell_price: float,
    demand_qty: float,
    buy_contract_price: float,
    bolsa_buy_price: float,
    bolsa_buy_kwh: float,
    margin_pct: float = 0.0,
) -> PriceLimitResult:
    """Compute the maximum acceptable bolsa purchase price for a market.

    price_limit = demand_sell_price × (1 - margin_pct/100)

    Buying from bolsa makes economic sense only when the bolsa price is below
    the price we'll receive from selling the energy to clients.  A positive
    margin_pct gives a buffer above breakeven.
    """
    # Blended avg sell price for the whole market (demand + bolsa-sell)
    total_qty = demand_qty + (bolsa_sell_price * 0)  # just demand for limit
    sell_avg = demand_sell_price  # use demand-side price as reference

    # Price limit = breakeven adjusted by margin
    price_limit = sell_avg * (1.0 - margin_pct / 100.0) if sell_avg > 0 else 0.0

    gap = bolsa_buy_price - price_limit
    is_above_limit = gap > 0

    loss_cop = -gap * bolsa_buy_kwh if is_above_limit else 0.0

    if is_above_limit:
        reco = (
            f"Bolsa {bolsa_buy_price:.0f} COP/kWh supera límite {price_limit:.0f} COP/kWh "
            f"(gap {gap:.0f} COP/kWh). Pérdida estimada: {loss_cop/1e6:.1f} M COP. "
            f"Negociar contratos de corto plazo o reducir exposición en bolsa."
        )
    else:
        reco = (
            f"Bolsa {bolsa_buy_price:.0f} COP/kWh está bajo límite {price_limit:.0f} COP/kWh. "
            f"Compra en bolsa es financieramente viable para {market_label}."
        )

    return PriceLimitResult(
        market=market_label,
        sell_demand_price=demand_sell_price,
        sell_bolsa_price=bolsa_sell_price,
        sell_avg_price=sell_avg,
        buy_contract_price=buy_contract_price,
        bolsa_buy_price=bolsa_buy_price,
        price_limit=price_limit,
        margin_pct=margin_pct,
        gap_cop_kwh=gap,
        is_above_limit=is_above_limit,
        bolsa_buy_kwh=bolsa_buy_kwh,
        loss_cop=loss_cop,
        recommendation=reco,
    )


def _build_sensitivity(
    bolsa_buy_kwh: float,
    current_bolsa_price: float,
    price_limit: float,
    steps: list[float] = None,
) -> list[SensitivityPoint]:
    """Generate sensitivity table for bolsa price scenarios."""
    if steps is None:
        steps = [-40, -30, -20, -15, -10, -5, 0, 5, 10, 15, 20, 30, 50]

    base_cost = bolsa_buy_kwh * current_bolsa_price
    points: list[SensitivityPoint] = []
    for pct in steps:
        scenario_price = current_bolsa_price * (1.0 + pct / 100.0)
        scenario_cost = bolsa_buy_kwh * scenario_price
        points.append(SensitivityPoint(
            price_scenario_cop_kwh=round(scenario_price, 1),
            additional_cost_cop=round(scenario_cost - base_cost, 0),
            total_bolsa_cost_cop=round(scenario_cost, 0),
            is_above_limit=scenario_price > price_limit,
        ))
    return points


def _generate_actions(
    balance_mwh: float,
    reg: PriceLimitResult,
    nr: PriceLimitResult,
) -> list[str]:
    actions: list[str] = []

    if reg.is_above_limit:
        actions.append(
            f"🔴 Regulado: precio bolsa ({reg.bolsa_buy_price:.0f}) supera límite "
            f"({reg.price_limit:.0f} COP/kWh) por {reg.gap_cop_kwh:.0f} COP/kWh. "
            f"Pérdida estimada {reg.loss_cop/1e6:.1f} M COP — buscar contratos de cobertura."
        )
    if nr.is_above_limit:
        actions.append(
            f"🔴 No Regulado: precio bolsa ({nr.bolsa_buy_price:.0f}) supera límite "
            f"({nr.price_limit:.0f} COP/kWh) por {nr.gap_cop_kwh:.0f} COP/kWh. "
            f"Pérdida estimada {nr.loss_cop/1e6:.1f} M COP — revisar cobertura contractual."
        )
    if balance_mwh > 0:
        actions.append(
            f"✅ Posición larga ({balance_mwh/1000:.1f} GWh): considera vender excedente "
            "en bolsa a precio favorable o mediante contratos spot."
        )
    elif balance_mwh < 0:
        actions.append(
            f"⚠️  Posición corta ({abs(balance_mwh)/1000:.1f} GWh): exposición en bolsa "
            "confirma necesidad de contratos adicionales de compra."
        )
    if not reg.is_above_limit and not nr.is_above_limit:
        actions.append("✅ Precio bolsa dentro del límite en ambos mercados.")

    return actions


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────

def run_curve_analysis(
    year: int,
    month: int,
    version_name: str,
    dashboard: dict,
    analysis: dict,
    income: dict,
    bolsa_summary: dict,
    margin_pct: float = 0.0,
) -> OptimizationResult:
    """Build buy/sell curves and price-limit results from pre-fetched API data."""

    # ── Curves ────────────────────────────────────────────────────────────────
    buy_curve = _build_buy_curve(analysis.get("scatter_contracts", []))
    sell_curve = _build_sell_curve(income.get("sections", []))

    # ── Bolsa volumes ─────────────────────────────────────────────────────────
    propio = bolsa_summary.get("propio", {})
    bolsa_buy_price = propio.get("buy_price", 0.0)
    bolsa_buy_kwh = propio.get("buy_qty", 0.0)
    bolsa_buy_cop = propio.get("buy_total", 0.0)

    # ── Market balance ────────────────────────────────────────────────────────
    mb = analysis.get("market_balance", {})
    reg_bolsa_buy_kwh = mb.get("regulado", {}).get("buy_bolsa", 0.0)
    nr_bolsa_buy_kwh = mb.get("no_regulado", {}).get("buy_bolsa", 0.0)

    # Buy contract avg prices from income statement
    compra_sec = next((s for s in income.get("sections", []) if s.get("id") == "compra"), {})
    reg_buy_price = 0.0
    nr_buy_price = 0.0
    for sub in compra_sec.get("sub_items", []):
        label = sub.get("label", "").lower()
        if "regulado" in label and "no" not in label:
            reg_buy_price = sub.get("precio_prom_cop", 0.0)
        elif "no" in label and "regulado" in label:
            nr_buy_price = sub.get("precio_prom_cop", 0.0)

    # Sell prices per market
    market_prices = _extract_market_prices(income.get("sections", []))

    # ── Price limits ──────────────────────────────────────────────────────────
    reg = _calc_price_limit_for_market(
        market_key="regulado",
        market_label="Regulado",
        demand_sell_price=market_prices["regulado"]["demand_price"],
        bolsa_sell_price=market_prices["regulado"]["bolsa_sell_price"],
        demand_qty=market_prices["regulado"]["demand_qty"],
        buy_contract_price=reg_buy_price,
        bolsa_buy_price=bolsa_buy_price,
        bolsa_buy_kwh=reg_bolsa_buy_kwh,
        margin_pct=margin_pct,
    )

    nr = _calc_price_limit_for_market(
        market_key="no_regulado",
        market_label="No Regulado",
        demand_sell_price=market_prices["no_regulado"]["demand_price"],
        bolsa_sell_price=market_prices["no_regulado"]["bolsa_sell_price"],
        demand_qty=market_prices["no_regulado"]["demand_qty"],
        buy_contract_price=nr_buy_price,
        bolsa_buy_price=bolsa_buy_price,
        bolsa_buy_kwh=nr_bolsa_buy_kwh,
        margin_pct=margin_pct,
    )

    global_limit = min(
        reg.price_limit if reg.price_limit > 0 else float("inf"),
        nr.price_limit if nr.price_limit > 0 else float("inf"),
    )
    if global_limit == float("inf"):
        global_limit = 0.0

    # ── Overall position ──────────────────────────────────────────────────────
    kpis = dashboard.get("kpis", {})
    balance_mwh = kpis.get("total", {}).get("balance_mwh", 0.0)

    # ── Sensitivity (use global limit as reference) ───────────────────────────
    sensitivity = _build_sensitivity(bolsa_buy_kwh, bolsa_buy_price, global_limit)

    # ── Total loss above limit ─────────────────────────────────────────────────
    total_loss = reg.loss_cop + nr.loss_cop

    return OptimizationResult(
        year=year,
        month=month,
        version_name=version_name,
        overall_balance_mwh=balance_mwh,
        is_long=balance_mwh >= 0,
        buy_curve=buy_curve,
        sell_curve=sell_curve,
        regulado=reg,
        no_regulado=nr,
        global_price_limit=global_limit,
        total_bolsa_buy_kwh=bolsa_buy_kwh,
        total_bolsa_buy_cop=bolsa_buy_cop,
        total_loss_above_limit_cop=total_loss,
        sensitivity=sensitivity,
        actions=_generate_actions(balance_mwh, reg, nr),
    )
