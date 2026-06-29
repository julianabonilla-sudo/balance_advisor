"""Computes day-over-day diffs between two daily snapshots and formats the report."""

from dataclasses import dataclass
from datetime import date
from typing import Optional

from .snapshot import DailySnapshot, MonthData


# ── Thresholds ────────────────────────────────────────────────────────────────
# Current month — normal market activity, higher tolerance
CURR_BALANCE_GWH     = 1.0    # GWh change in balance
CURR_COVERAGE_PP     = 2.0    # pp change in coverage
CURR_BOLSA_PCT       = 5.0    # % change in bolsa buy

# Future months — should be stable (contracts fixed); tighter tolerance
FWD_BALANCE_GWH      = 0.5    # GWh — any movement is notable
FWD_COVERAGE_PP      = 1.5    # pp
FWD_BOLSA_PCT        = 3.0    # %


@dataclass
class FieldChange:
    field: str
    label: str
    prev: float
    curr: float
    delta: float
    unit: str           # unit for the delta (e.g. "pp", "GWh")
    value_unit: str     # unit for the prev/curr display (e.g. "%", "GWh")
    is_critical: bool


@dataclass
class MonthDiff:
    year: int
    month: int
    is_current: bool
    changes: list[FieldChange]

    @property
    def has_changes(self) -> bool:
        return bool(self.changes)

    @property
    def is_critical(self) -> bool:
        return any(c.is_critical for c in self.changes)


@dataclass
class DailyDiff:
    date_prev: str
    date_curr: str
    month_diffs: list[MonthDiff]

    @property
    def current_diffs(self) -> list[MonthDiff]:
        return [m for m in self.month_diffs if m.is_current and m.has_changes]

    @property
    def forward_diffs(self) -> list[MonthDiff]:
        return [m for m in self.month_diffs if not m.is_current and m.has_changes]

    @property
    def has_any_change(self) -> bool:
        return any(m.has_changes for m in self.month_diffs)

    @property
    def has_critical(self) -> bool:
        return any(m.is_critical for m in self.month_diffs)


def _pct_change(prev: float, curr: float) -> float:
    if abs(prev) < 0.001:
        return 0.0
    return (curr - prev) / abs(prev) * 100


def _check_month(prev: MonthData, curr: MonthData) -> MonthDiff:
    changes: list[FieldChange] = []
    is_curr = curr.is_current

    bal_thresh  = CURR_BALANCE_GWH  if is_curr else FWD_BALANCE_GWH
    cov_thresh  = CURR_COVERAGE_PP  if is_curr else FWD_COVERAGE_PP
    bol_thresh  = CURR_BOLSA_PCT    if is_curr else FWD_BOLSA_PCT

    delta_bal = (curr.balance_mwh - prev.balance_mwh) / 1_000      # GWh
    if abs(delta_bal) >= bal_thresh:
        changes.append(FieldChange(
            field="balance", label="Balance neto",
            prev=prev.balance_mwh / 1_000, curr=curr.balance_mwh / 1_000,
            delta=delta_bal, unit="GWh", value_unit="GWh",
            is_critical=abs(delta_bal) >= bal_thresh * 2,
        ))

    for mkt, p_cov, c_cov in [
        ("regulado",    prev.coverage_reg_pct, curr.coverage_reg_pct),
        ("no regulado", prev.coverage_nr_pct,  curr.coverage_nr_pct),
    ]:
        delta_cov = c_cov - p_cov
        if abs(delta_cov) >= cov_thresh:
            changes.append(FieldChange(
                field=f"cov_{mkt}", label=f"Cobertura {mkt}",
                prev=p_cov, curr=c_cov, delta=delta_cov, unit="pp", value_unit="%",
                is_critical=abs(delta_cov) >= cov_thresh * 2,
            ))

    delta_bol_pct = _pct_change(prev.bolsa_buy_mwh, curr.bolsa_buy_mwh)
    delta_bol_gwh = (curr.bolsa_buy_mwh - prev.bolsa_buy_mwh) / 1_000
    if abs(delta_bol_pct) >= bol_thresh and abs(delta_bol_gwh) >= 0.1:
        changes.append(FieldChange(
            field="bolsa", label="Compra bolsa",
            prev=prev.bolsa_buy_mwh / 1_000, curr=curr.bolsa_buy_mwh / 1_000,
            delta=delta_bol_gwh, unit="GWh", value_unit="GWh",
            is_critical=abs(delta_bol_pct) >= bol_thresh * 2,
        ))

    return MonthDiff(year=curr.year, month=curr.month, is_current=is_curr, changes=changes)


def compute_diff(prev: DailySnapshot, curr: DailySnapshot) -> DailyDiff:
    prev_map = {(m.year, m.month): m for m in prev.months}
    curr_map = {(m.year, m.month): m for m in curr.months}

    diffs = []
    for key, c in curr_map.items():
        p = prev_map.get(key)
        if p is None:
            continue
        diffs.append(_check_month(p, c))

    diffs.sort(key=lambda d: (d.year, d.month))
    return DailyDiff(date_prev=prev.snapshot_date, date_curr=curr.snapshot_date, month_diffs=diffs)


# ── Report builder ────────────────────────────────────────────────────────────

def _sign(v: float) -> str:
    return f"+{v:.2f}" if v >= 0 else f"{v:.2f}"


def _arrow(delta: float) -> str:
    return "▲" if delta > 0 else "▼"


def _sev(c: FieldChange) -> str:
    return "🔴" if c.is_critical else "🟡"


def build_diff_report(diff: DailyDiff, today: Optional[date] = None) -> str:
    W = 64
    lines: list[str] = []

    def div(ch="═"):
        lines.append(ch * W)

    def blank():
        lines.append("")

    def section(title):
        blank()
        lines.append("▌ " + title)
        lines.append("  " + "─" * (W - 2))

    today = today or date.today()

    # Header
    div()
    lines.append("⚡ ENERGY BALANCE ADVISOR — MONITOR DIARIO")
    lines.append(f"   {diff.date_curr}  |  vs  {diff.date_prev}")
    div()
    blank()

    if not diff.has_any_change:
        lines.append("  🟢  Sin cambios materiales vs ayer. Posición estable.")
        blank()
        div()
        lines.append(f"  Fuente: API Olibia Energy  |  {today}")
        div()
        return "\n".join(lines)

    status = "🔴 CAMBIOS CRÍTICOS DETECTADOS" if diff.has_critical else "🟡 CAMBIOS MODERADOS DETECTADOS"
    n_curr = len(diff.current_diffs)
    n_fwd  = len(diff.forward_diffs)
    lines.append(f"  Estado  : {status}")
    lines.append(f"  Mes actual : {n_curr} cambios  |  Horizonte futuro : {n_fwd} meses con cambios")

    # ── 1. Mes actual
    section("1.  MES ACTUAL  —  CAMBIOS VS AYER")
    if not diff.current_diffs:
        lines.append("  🟢  Sin cambios materiales en el mes actual.")
    else:
        for md in diff.current_diffs:
            label = f"{md.year}-{md.month:02d}"
            for c in md.changes:
                arrow = _arrow(c.delta)
                lines.append(
                    f"  {_sev(c)}  {c.label:<22}"
                    f"  {c.prev:>8.2f} {c.value_unit} → {c.curr:>7.2f} {c.value_unit}"
                    f"  ({_sign(c.delta)} {c.unit})  {arrow}"
                )

    # ── 2. Horizonte futuro
    section("2.  HORIZONTE 18 MESES  —  CAMBIOS EN INSUMOS")
    lines.append("  Los meses futuros deben ser estables. Cualquier cambio")
    lines.append("  indica modificación de contratos o proyecciones de demanda.")
    blank()

    if not diff.forward_diffs:
        lines.append("  🟢  Sin cambios en los meses futuros. Insumos estables.")
    else:
        for md in sorted(diff.forward_diffs, key=lambda m: (m.year, m.month)):
            from datetime import date as d
            label = d(md.year, md.month, 1).strftime("%b %Y")
            sev_icon = "🔴" if md.is_critical else "🟡"
            lines.append(f"  {sev_icon}  {label}")
            for c in md.changes:
                arrow = _arrow(c.delta)
                lines.append(
                    f"       {c.label:<22}"
                    f"  {c.prev:>8.2f} {c.value_unit} → {c.curr:>7.2f} {c.value_unit}"
                    f"  ({_sign(c.delta)} {c.unit})  {arrow}"
                )

    # ── 3. Resumen accionable
    section("3.  ACCIONES")
    if diff.has_critical:
        lines.append("  🔴  Hay cambios críticos — revisar posición antes de operar.")
    if diff.forward_diffs:
        lines.append(f"  ⚠️   {len(diff.forward_diffs)} mes(es) futuros cambiaron insumos — validar con el equipo.")
    if not diff.has_critical and not diff.forward_diffs:
        lines.append("  🟡  Cambios moderados en el mes actual. Monitorear evolución.")

    blank()
    div()
    lines.append(f"  Fuente: API Olibia Energy  |  {today}")
    div()
    blank()

    return "\n".join(lines)
