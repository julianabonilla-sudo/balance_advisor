"""Alert engine — detects critical deviations in the energy balance.

Checks run against live API data and return structured Alert objects
classified by severity. Thresholds are configurable via AlertConfig.

Posición energética se expresa siempre como:
  - balance < 0  →  "Compra en bolsa" (kWh, positivo)
  - balance > 0  →  "Venta en bolsa"  (kWh, positivo)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    CRITICAL = "CRITICA"
    WARNING = "ATENCION"
    OK = "OK"


class Category(str, Enum):
    EXPOSURE = "exposicion"
    PRICE = "precio"
    DEMAND = "demanda"
    CONTRACT = "contrato"
    DELTA = "variacion_diaria"
    TREND = "tendencia_mensual"


@dataclass
class Alert:
    severity: Severity
    category: Category
    market: str          # "regulado" | "no_regulado" | "total"
    message: str
    value: float
    threshold: float
    unit: str
    detail: Optional[str] = None


@dataclass
class AlertConfig:
    # Daily delta thresholds — % change in bolsa buy vs previous day
    delta_warning_pct: float = 3.0      # sube > 3% vs ayer → ATENCIÓN
    delta_critical_pct: float = 10.0    # sube > 10% vs ayer → CRÍTICA

    # Financial impact thresholds (COP)
    impact_critical_cop: float = -50_000_000    # -50 M COP → CRÍTICA
    impact_warning_cop: float = -15_000_000     # -15 M COP → ATENCIÓN

    # Bolsa price thresholds (COP/kWh)
    price_spike_critical: float = 700.0
    price_spike_warning: float = 600.0

    # Demand coverage ratio (contracts / demand)
    coverage_critical_pct: float = 70.0
    coverage_warning_pct: float = 85.0

    # Hourly exposure: número de horas críticas que dispara alerta
    critical_hours_threshold: int = 10

    # Forward trend thresholds — month-over-month change across next 12 months
    trend_bolsa_warning_pct: float = 20.0    # compra bolsa sube > 20% vs mes anterior → ATENCIÓN
    trend_bolsa_critical_pct: float = 40.0   # compra bolsa sube > 40% vs mes anterior → CRÍTICA
    trend_coverage_warning_drop_pp: float = 5.0   # cobertura cae > 5 pp vs mes anterior → ATENCIÓN
    trend_coverage_critical_drop_pp: float = 10.0 # cobertura cae > 10 pp vs mes anterior → CRÍTICA


@dataclass
class AlertReport:
    year: int
    month: int
    version_name: str
    alerts: list[Alert] = field(default_factory=list)

    @property
    def critical(self) -> list[Alert]:
        return [a for a in self.alerts if a.severity == Severity.CRITICAL]

    @property
    def warnings(self) -> list[Alert]:
        return [a for a in self.alerts if a.severity == Severity.WARNING]

    @property
    def has_critical(self) -> bool:
        return bool(self.critical)

    def summary(self) -> str:
        emoji = "🔴" if self.has_critical else ("🟡" if self.warnings else "🟢")
        lines = [
            f"{emoji} Reporte de Alertas — {self.month:02d}/{self.year} | {self.version_name}",
            f"  {len(self.critical)} críticas · {len(self.warnings)} advertencias",
        ]
        for a in self.alerts:
            icon = "🔴" if a.severity == Severity.CRITICAL else "🟡"
            lines.append(f"  {icon} [{a.category.value.upper()}] {a.message}")
            if a.detail:
                lines.append(f"     → {a.detail}")
        return "\n".join(lines)


def balance_to_bolsa(balance_mwh: float) -> tuple[str, float]:
    """Convert balance_mwh to a (label, kWh) tuple for display."""
    kwh = abs(balance_mwh) * 1000
    label = "Compra en bolsa" if balance_mwh < 0 else "Venta en bolsa"
    return label, kwh


def run_alerts(
    year: int,
    month: int,
    version_name: str,
    dashboard: dict,
    matrix: dict,
    analysis: dict,
    config: AlertConfig = None,
) -> AlertReport:
    """Run all alert checks and return a consolidated report."""
    if config is None:
        config = AlertConfig()

    report = AlertReport(year=year, month=month, version_name=version_name)

    _check_bolsa_position(report, dashboard, config)
    _check_daily_delta(report, dashboard, config)
    _check_financial_impact(report, dashboard, config)
    _check_demand_coverage(report, dashboard, config)
    _check_bolsa_prices(report, analysis, config)
    _check_hourly_exposure(report, matrix, config)

    return report


# ── Individual checks ────────────────────────────────────────────────────────

def _check_bolsa_position(report: AlertReport, dashboard: dict, cfg: AlertConfig):
    """Report current bolsa position as buy/sell in kWh — no fixed threshold, purely informational."""
    kpis = dashboard.get("kpis", {})
    for market in ("regulado", "no_regulado", "total"):
        balance_mwh = kpis.get(market, {}).get("balance_mwh", 0)
        if balance_mwh == 0:
            continue
        label, kwh = balance_to_bolsa(balance_mwh)
        # Only alert if it's a buy (deficit) — sells are informational
        if balance_mwh < 0:
            severity = Severity.CRITICAL if kwh > 2_000_000 else Severity.WARNING
            report.alerts.append(Alert(
                severity=severity,
                category=Category.EXPOSURE,
                market=market,
                message=f"{label}: {kwh:,.0f} kWh en mercado {market}",
                value=kwh,
                threshold=0,
                unit="kWh",
                detail=f"Equivale a {abs(balance_mwh):,.1f} MWh que se deben cubrir comprando en bolsa",
            ))


def _check_daily_delta(report: AlertReport, dashboard: dict, cfg: AlertConfig):
    """Alert when today's bolsa buy increased significantly vs the previous day."""
    daily = dashboard.get("daily_balance", [])
    # Filter days with actual data (bolsa_buy > 0 in either market)
    active_days = [
        d for d in daily
        if d.get("bolsa_buy_r", 0) + d.get("bolsa_buy_nr", 0) > 0
    ]
    if len(active_days) < 2:
        return

    prev = active_days[-2]
    curr = active_days[-1]

    for market_key, r_key, nr_key, label in [
        ("regulado",    "bolsa_buy_r",  None,         "regulado"),
        ("no_regulado", None,           "bolsa_buy_nr","no regulado"),
        ("total",       "bolsa_buy_r",  "bolsa_buy_nr","total"),
    ]:
        def total(d):
            v = 0
            if r_key:
                v += d.get(r_key, 0)
            if nr_key:
                v += d.get(nr_key, 0)
            return v

        prev_val = total(prev)
        curr_val = total(curr)

        if prev_val == 0:
            continue

        delta_pct = ((curr_val - prev_val) / prev_val) * 100

        if delta_pct >= cfg.delta_critical_pct:
            report.alerts.append(Alert(
                severity=Severity.CRITICAL,
                category=Category.DELTA,
                market=market_key,
                message=f"Compra en bolsa subió {delta_pct:.1f}% vs día anterior — mercado {label}",
                value=delta_pct,
                threshold=cfg.delta_critical_pct,
                unit="%",
                detail=(
                    f"Día {prev.get('day')}: {prev_val/1000:,.0f} kWh → "
                    f"Día {curr.get('day')}: {curr_val/1000:,.0f} kWh"
                ),
            ))
        elif delta_pct >= cfg.delta_warning_pct:
            report.alerts.append(Alert(
                severity=Severity.WARNING,
                category=Category.DELTA,
                market=market_key,
                message=f"Compra en bolsa subió {delta_pct:.1f}% vs día anterior — mercado {label}",
                value=delta_pct,
                threshold=cfg.delta_warning_pct,
                unit="%",
                detail=(
                    f"Día {prev.get('day')}: {prev_val/1000:,.0f} kWh → "
                    f"Día {curr.get('day')}: {curr_val/1000:,.0f} kWh"
                ),
            ))


def _check_financial_impact(report: AlertReport, dashboard: dict, cfg: AlertConfig):
    kpis = dashboard.get("kpis", {})
    for market in ("regulado", "no_regulado", "total"):
        impact = kpis.get(market, {}).get("impact_cop", 0)
        impact_m = impact / 1_000_000

        if impact < cfg.impact_critical_cop:
            report.alerts.append(Alert(
                severity=Severity.CRITICAL,
                category=Category.PRICE,
                market=market,
                message=f"Impacto financiero crítico en mercado {market}: {impact_m:,.0f} M COP",
                value=impact,
                threshold=cfg.impact_critical_cop,
                unit="COP",
                detail=f"Umbral: {cfg.impact_critical_cop / 1_000_000:,.0f} M COP",
            ))
        elif impact < cfg.impact_warning_cop:
            report.alerts.append(Alert(
                severity=Severity.WARNING,
                category=Category.PRICE,
                market=market,
                message=f"Impacto financiero alto en mercado {market}: {impact_m:,.0f} M COP",
                value=impact,
                threshold=cfg.impact_warning_cop,
                unit="COP",
            ))


def _check_demand_coverage(report: AlertReport, dashboard: dict, cfg: AlertConfig):
    kpis = dashboard.get("kpis", {})
    for market in ("regulado", "no_regulado"):
        data = kpis.get(market, {})
        contracts = data.get("contracts_mwh", 0)
        demand = data.get("demand_mwh", 0)
        if demand == 0:
            continue
        coverage_pct = (contracts / demand) * 100

        if coverage_pct < cfg.coverage_critical_pct:
            report.alerts.append(Alert(
                severity=Severity.CRITICAL,
                category=Category.CONTRACT,
                market=market,
                message=f"Cobertura contractual crítica en mercado {market}: {coverage_pct:.1f}%",
                value=coverage_pct,
                threshold=cfg.coverage_critical_pct,
                unit="%",
                detail=f"Contratos: {contracts:,.0f} MWh vs. demanda: {demand:,.0f} MWh",
            ))
        elif coverage_pct < cfg.coverage_warning_pct:
            report.alerts.append(Alert(
                severity=Severity.WARNING,
                category=Category.CONTRACT,
                market=market,
                message=f"Cobertura contractual baja en mercado {market}: {coverage_pct:.1f}%",
                value=coverage_pct,
                threshold=cfg.coverage_warning_pct,
                unit="%",
                detail=f"Contratos: {contracts:,.0f} MWh vs. demanda: {demand:,.0f} MWh",
            ))


def _check_bolsa_prices(report: AlertReport, analysis: dict, cfg: AlertConfig):
    daily_bolsa = analysis.get("daily_bolsa", [])
    if not daily_bolsa:
        return

    spike_critical = [d for d in daily_bolsa if d.get("price", 0) >= cfg.price_spike_critical]
    spike_warning = [
        d for d in daily_bolsa
        if cfg.price_spike_warning <= d.get("price", 0) < cfg.price_spike_critical
    ]

    if spike_critical:
        worst = max(spike_critical, key=lambda d: d["price"])
        report.alerts.append(Alert(
            severity=Severity.CRITICAL,
            category=Category.PRICE,
            market="total",
            message=f"Precio de bolsa extremo: {worst['price']:,.1f} COP/kWh ({len(spike_critical)} días)",
            value=worst["price"],
            threshold=cfg.price_spike_critical,
            unit="COP/kWh",
            detail=f"Peor día: {worst.get('date', worst.get('day'))} — compras: {worst.get('buy_mwh', 0):,.1f} MWh",
        ))
    elif spike_warning:
        worst = max(spike_warning, key=lambda d: d["price"])
        report.alerts.append(Alert(
            severity=Severity.WARNING,
            category=Category.PRICE,
            market="total",
            message=f"Precio de bolsa alto: hasta {worst['price']:,.1f} COP/kWh ({len(spike_warning)} días)",
            value=worst["price"],
            threshold=cfg.price_spike_warning,
            unit="COP/kWh",
        ))


def _check_hourly_exposure(report: AlertReport, matrix: dict, cfg: AlertConfig):
    cells = matrix.get("cells", [])
    # Only cells where balance is negative (need to buy in bolsa)
    buy_cells = [c for c in cells if c.get("balance_reg_kwh", 0) < 0 or c.get("balance_noreg_kwh", 0) < 0]

    if len(buy_cells) > cfg.critical_hours_threshold:
        worst = min(buy_cells, key=lambda c: min(
            c.get("balance_reg_kwh", 0),
            c.get("balance_noreg_kwh", 0),
        ))
        worst_kwh = abs(min(
            worst.get("balance_reg_kwh", 0),
            worst.get("balance_noreg_kwh", 0),
        ))
        report.alerts.append(Alert(
            severity=Severity.CRITICAL,
            category=Category.EXPOSURE,
            market="total",
            message=f"{len(buy_cells)} horas con compra en bolsa requerida",
            value=len(buy_cells),
            threshold=cfg.critical_hours_threshold,
            unit="horas",
            detail=(
                f"Peor hora: día {worst['day']} hora {worst['hour']} — "
                f"Compra en bolsa: {worst_kwh:,.0f} kWh"
            ),
        ))
    elif buy_cells:
        report.alerts.append(Alert(
            severity=Severity.WARNING,
            category=Category.EXPOSURE,
            market="total",
            message=f"{len(buy_cells)} horas con compra en bolsa requerida",
            value=len(buy_cells),
            threshold=cfg.critical_hours_threshold,
            unit="horas",
        ))


# ── Forward trend (12-month horizon) ────────────────────────────────────────

@dataclass
class MonthSnapshot:
    year: int
    month: int
    version_name: str
    contracts_mwh: float          # inventario total de contratos
    portfolio_mwh: float          # portafolio disponible (contratos - vendidos)
    bolsa_buy_mwh: float          # compra en bolsa del mes (0 en meses sin demanda)
    bolsa_buy_cop: float          # costo total bolsa
    coverage_reg_pct: float       # cobertura regulado % (0 si no hay demanda)
    coverage_nr_pct: float        # cobertura no regulado % (0 si no hay demanda)
    balance_mwh: float            # posición neta total
    has_demand: bool = False      # True si el mes tiene datos de demanda reales


@dataclass
class ForwardTrendReport:
    snapshots: list[MonthSnapshot]
    alerts: list[Alert]

    @property
    def critical(self) -> list[Alert]:
        return [a for a in self.alerts if a.severity == Severity.CRITICAL]

    @property
    def warnings(self) -> list[Alert]:
        return [a for a in self.alerts if a.severity == Severity.WARNING]

    def summary(self) -> str:
        emoji = "🔴" if self.critical else ("🟡" if self.warnings else "🟢")
        lines = [
            f"{emoji} Tendencia 12 meses — {len(self.snapshots)} períodos analizados",
            f"  {len(self.critical)} críticas · {len(self.warnings)} advertencias",
        ]
        for a in self.alerts:
            icon = "🔴" if a.severity == Severity.CRITICAL else "🟡"
            lines.append(f"  {icon} [{a.market}] {a.message}")
            if a.detail:
                lines.append(f"     → {a.detail}")
        return "\n".join(lines)


def build_month_snapshot(year: int, month: int, version_name: str, dashboard: dict) -> MonthSnapshot:
    kpis = dashboard.get("kpis", {})

    reg = kpis.get("regulado", {})
    nr = kpis.get("no_regulado", {})
    total = kpis.get("total", {})

    demand_total = total.get("demand_mwh", 0)
    has_demand = demand_total > 0

    def coverage(data: dict) -> float:
        demand = data.get("demand_mwh", 0)
        if demand == 0:
            return 0.0
        return (data.get("contracts_mwh", 0) / demand) * 100

    return MonthSnapshot(
        year=year,
        month=month,
        version_name=version_name,
        contracts_mwh=total.get("contracts_mwh", 0),
        portfolio_mwh=total.get("available_portfolio_mwh", 0),
        bolsa_buy_mwh=total.get("bolsa_buy_mwh", 0),
        bolsa_buy_cop=total.get("bolsa_buy_cop", 0),
        coverage_reg_pct=coverage(reg),
        coverage_nr_pct=coverage(nr),
        balance_mwh=total.get("balance_mwh", 0),
        has_demand=has_demand,
    )


def check_forward_trend(
    snapshots: list[MonthSnapshot],
    config: AlertConfig = None,
) -> ForwardTrendReport:
    """Compare consecutive months and alert on worsening trends.

    Two passes:
    1. Absolute position check — fires on any month that is already in a bad
       state regardless of how it got there.
    2. Delta check — fires when a month is significantly worse than the prior.
    """
    if config is None:
        config = AlertConfig()

    alerts: list[Alert] = []

    # ── Pass 1: absolute position for every snapshot ──────────────────────────
    for s in snapshots:
        label = f"{s.year}-{s.month:02d}"

        # Short balance (absolute)
        if s.balance_mwh < -5_000:
            alerts.append(Alert(
                severity=Severity.CRITICAL,
                category=Category.TREND,
                market="total",
                message=f"{label}: posición corta crítica — balance {s.balance_mwh:,.1f} MWh",
                value=s.balance_mwh,
                threshold=-5_000,
                unit="MWh",
                detail=(
                    f"Compra en bolsa proyectada: {s.bolsa_buy_mwh:,.1f} MWh. "
                    f"Portfolio disponible insuficiente para cubrir demanda."
                ),
            ))
        elif s.balance_mwh < -2_000:
            alerts.append(Alert(
                severity=Severity.WARNING,
                category=Category.TREND,
                market="total",
                message=f"{label}: posición corta — balance {s.balance_mwh:,.1f} MWh",
                value=s.balance_mwh,
                threshold=-2_000,
                unit="MWh",
                detail=f"Compra en bolsa proyectada: {s.bolsa_buy_mwh:,.1f} MWh.",
            ))

        # Low coverage (absolute) — only meaningful when there is demand
        if s.has_demand:
            for mkt, cov in [("regulado", s.coverage_reg_pct), ("no_regulado", s.coverage_nr_pct)]:
                if cov == 0:
                    continue
                if cov < config.coverage_critical_pct:
                    alerts.append(Alert(
                        severity=Severity.CRITICAL,
                        category=Category.TREND,
                        market=mkt,
                        message=f"{label}: cobertura {mkt} baja — {cov:.1f}% (crítico < {config.coverage_critical_pct:.0f}%)",
                        value=cov,
                        threshold=config.coverage_critical_pct,
                        unit="%",
                        detail=f"Portfolio contratos insuficiente para cubrir la demanda {mkt}.",
                    ))
                elif cov < config.coverage_warning_pct:
                    alerts.append(Alert(
                        severity=Severity.WARNING,
                        category=Category.TREND,
                        market=mkt,
                        message=f"{label}: cobertura {mkt} reducida — {cov:.1f}% (atención < {config.coverage_warning_pct:.0f}%)",
                        value=cov,
                        threshold=config.coverage_warning_pct,
                        unit="%",
                    ))

    # ── Pass 2: delta between consecutive months ───────────────────────────────
    for i in range(1, len(snapshots)):
        prev = snapshots[i - 1]
        curr = snapshots[i]
        label = f"{curr.year}-{curr.month:02d}"
        prev_label = f"{prev.year}-{prev.month:02d}"

        if curr.has_demand and prev.has_demand:
            # Months with real demand: check bolsa buy increase and coverage drop
            if prev.bolsa_buy_mwh > 0:
                delta_pct = ((curr.bolsa_buy_mwh - prev.bolsa_buy_mwh) / prev.bolsa_buy_mwh) * 100
                if delta_pct >= config.trend_bolsa_critical_pct:
                    alerts.append(Alert(
                        severity=Severity.CRITICAL,
                        category=Category.TREND,
                        market="total",
                        message=f"{label}: compra en bolsa sube {delta_pct:.1f}% vs {prev_label}",
                        value=delta_pct,
                        threshold=config.trend_bolsa_critical_pct,
                        unit="%",
                        detail=f"{prev_label}: {prev.bolsa_buy_mwh:,.1f} MWh → {label}: {curr.bolsa_buy_mwh:,.1f} MWh",
                    ))
                elif delta_pct >= config.trend_bolsa_warning_pct:
                    alerts.append(Alert(
                        severity=Severity.WARNING,
                        category=Category.TREND,
                        market="total",
                        message=f"{label}: compra en bolsa sube {delta_pct:.1f}% vs {prev_label}",
                        value=delta_pct,
                        threshold=config.trend_bolsa_warning_pct,
                        unit="%",
                        detail=f"{prev_label}: {prev.bolsa_buy_mwh:,.1f} MWh → {label}: {curr.bolsa_buy_mwh:,.1f} MWh",
                    ))

            for mkt, prev_cov, curr_cov in [
                ("regulado",    prev.coverage_reg_pct, curr.coverage_reg_pct),
                ("no_regulado", prev.coverage_nr_pct,  curr.coverage_nr_pct),
            ]:
                drop = prev_cov - curr_cov
                if drop >= config.trend_coverage_critical_drop_pp:
                    alerts.append(Alert(
                        severity=Severity.CRITICAL,
                        category=Category.TREND,
                        market=mkt,
                        message=f"{label}: cobertura {mkt} cae {drop:.1f} pp vs {prev_label}",
                        value=drop,
                        threshold=config.trend_coverage_critical_drop_pp,
                        unit="pp",
                        detail=f"{prev_label}: {prev_cov:.1f}% → {label}: {curr_cov:.1f}%",
                    ))
                elif drop >= config.trend_coverage_warning_drop_pp:
                    alerts.append(Alert(
                        severity=Severity.WARNING,
                        category=Category.TREND,
                        market=mkt,
                        message=f"{label}: cobertura {mkt} cae {drop:.1f} pp vs {prev_label}",
                        value=drop,
                        threshold=config.trend_coverage_warning_drop_pp,
                        unit="pp",
                        detail=f"{prev_label}: {prev_cov:.1f}% → {label}: {curr_cov:.1f}%",
                    ))

        else:
            # Future months without demand: track portfolio inventory drop
            if prev.portfolio_mwh > 0:
                portfolio_drop_pct = ((prev.portfolio_mwh - curr.portfolio_mwh) / prev.portfolio_mwh) * 100
                if portfolio_drop_pct >= config.trend_bolsa_critical_pct:
                    alerts.append(Alert(
                        severity=Severity.CRITICAL,
                        category=Category.TREND,
                        market="total",
                        message=f"{label}: portafolio disponible cae {portfolio_drop_pct:.1f}% vs {prev_label}",
                        value=portfolio_drop_pct,
                        threshold=config.trend_bolsa_critical_pct,
                        unit="%",
                        detail=(
                            f"{prev_label}: {prev.portfolio_mwh:,.0f} MWh → "
                            f"{label}: {curr.portfolio_mwh:,.0f} MWh — "
                            f"posible vencimiento de contratos"
                        ),
                    ))
                elif portfolio_drop_pct >= config.trend_bolsa_warning_pct:
                    alerts.append(Alert(
                        severity=Severity.WARNING,
                        category=Category.TREND,
                        market="total",
                        message=f"{label}: portafolio disponible cae {portfolio_drop_pct:.1f}% vs {prev_label}",
                        value=portfolio_drop_pct,
                        threshold=config.trend_bolsa_warning_pct,
                        unit="%",
                        detail=(
                            f"{prev_label}: {prev.portfolio_mwh:,.0f} MWh → "
                            f"{label}: {curr.portfolio_mwh:,.0f} MWh"
                        ),
                    ))

    return ForwardTrendReport(snapshots=snapshots, alerts=alerts)
