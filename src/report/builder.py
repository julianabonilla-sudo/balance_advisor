"""Formats the executive report from pre-computed analysis results."""

import re
from dataclasses import dataclass
from datetime import date

from src.alerts.engine import AlertReport, ForwardTrendReport, Severity
from src.curves.engine import OptimizationResult
from src.contracts.expiry import ExpiryCalendar

# ── Display helpers ───────────────────────────────────────────────────────────

def _gwh(mwh: float, decimals: int = 1) -> str:
    """MWh → GWh string."""
    return f"{mwh / 1_000:.{decimals}f} GWh"

def _gwh_k(kwh: float, decimals: int = 1) -> str:
    """kWh → GWh string."""
    return _gwh(kwh / 1_000, decimals)

def _mcop(cop: float) -> str:
    return f"{cop / 1_000_000:,.1f} M COP"

def _pct(v: float) -> str:
    return f"{v:.0f}%"

def _cov_icon(pct: float) -> str:
    if pct < 70:   return "🔴"
    if pct < 85:   return "🟡"
    return "🟢"

def _bal_icon(mwh: float) -> str:
    if mwh < -5_000: return "🔴"
    if mwh < 0:      return "🟡"
    return "🟢"

def _bar(pct: float, width: int = 20, cap: int = 200) -> str:
    """ASCII progress bar capped at cap%."""
    filled = min(int(pct / cap * width), width)
    bar = "█" * filled + "░" * (width - filled)
    return f"|{bar}|"

def _sev_icon(s: Severity) -> str:
    return "🔴" if s == Severity.CRITICAL else "🟡"


_MWH_PATTERN = re.compile(r"([\d,]+\.?\d*)\s*MWh")
_KWH_LARGE_PATTERN = re.compile(r"([\d,]+\.?\d*)\s*kWh")

def _to_gwh(text: str) -> str:
    """Convert large MWh and kWh quantities in alert text to GWh."""
    def _mwh(m: re.Match) -> str:
        return f"{float(m.group(1).replace(',', '')) / 1_000:.2f} GWh"

    def _kwh(m: re.Match) -> str:
        num = float(m.group(1).replace(",", ""))
        if num >= 500_000:  # ≥ 0.5 GWh → convert
            return f"{num / 1_000_000:.2f} GWh"
        return m.group(0)   # keep small hourly kWh values as-is

    text = _MWH_PATTERN.sub(_mwh, text)
    text = _KWH_LARGE_PATTERN.sub(_kwh, text)
    return text


# ── Report data container ─────────────────────────────────────────────────────

@dataclass
class ReportData:
    generated_at: date
    year: int
    month: int
    version_name: str
    alert_report: AlertReport
    forward_report: ForwardTrendReport
    opt_result: OptimizationResult
    expiry_calendar: ExpiryCalendar
    coverage_rows: list[dict]   # per-market monthly coverage for next 12 months
    current_reg_cov: float = 0.0    # regulado coverage % for the reference month
    current_nr_cov: float = 0.0     # no_regulado coverage % for the reference month


# ── Main builder ──────────────────────────────────────────────────────────────

def build_report(data: ReportData) -> str:
    lines: list[str] = []
    W = 64  # total width

    def div(char: str = "═"):
        lines.append(char * W)

    def blank():
        lines.append("")

    def section(title: str):
        blank()
        lines.append("▌ " + title)
        lines.append("  " + "─" * (W - 2))

    opt = data.opt_result
    fwd = data.forward_report
    cal = data.expiry_calendar
    month_name = date(data.year, data.month, 1).strftime("%b %Y").upper()

    # ── Header ────────────────────────────────────────────────────────────────
    div()
    lines.append(f"⚡ ENERGY BALANCE ADVISOR — REPORTE EJECUTIVO")
    lines.append(f"   {month_name} ({data.version_name})  |  Generado: {data.generated_at}")
    div()

    # ── Semáforo global ───────────────────────────────────────────────────────
    n_crit = len(data.alert_report.critical)
    n_warn = len(data.alert_report.warnings)
    n_fwd  = len(fwd.critical)
    icon   = "🔴 CRÍTICO" if n_crit > 0 else ("🟡 ATENCIÓN" if n_warn > 0 else "🟢 OK")
    blank()
    lines.append(f"  Estado general : {icon}  ({n_crit} críticas · {n_warn} advertencias este mes)")
    lines.append(f"  Tendencia 18m  : {n_fwd} alertas críticas en el horizonte")

    # ── 1. Posición del mes ───────────────────────────────────────────────────
    section("1.  POSICIÓN DEL MES")

    bal_gwh  = opt.overall_balance_mwh / 1_000
    buy_gwh  = opt.total_bolsa_buy_kwh / 1_000 / 1_000
    cost_cop = opt.total_bolsa_buy_cop
    pos_lbl  = "LARGO ✅" if opt.is_long else "CORTO 🔴"

    lines.append(f"  Balance neto     {bal_gwh:+.2f} GWh   →  {pos_lbl}")
    lines.append(f"  Compra en bolsa  {buy_gwh:.2f} GWh   a  {opt.regulado.bolsa_buy_price:.0f} COP/kWh")
    lines.append(f"  Costo bolsa      {_mcop(cost_cop)}")
    blank()
    lines.append(f"  {'Mercado':<14} {'Precio venta':>13} {'Precio límite':>14} {'Precio bolsa':>13} {'Gap':>8}  {'Pérdida':>12}")
    lines.append(f"  {'':─<14} {'':─>13} {'':─>14} {'':─>13} {'':─>8}  {'':─>12}")
    for mkt in [opt.regulado, opt.no_regulado]:
        flag = "⚠️ " if mkt.is_above_limit else "✅ "
        loss = _mcop(mkt.loss_cop) if mkt.is_above_limit else "—"
        lines.append(
            f"  {mkt.market:<14} {mkt.sell_demand_price:>10.0f} c/k"
            f"  {mkt.price_limit:>10.0f} c/k"
            f"  {mkt.bolsa_buy_price:>10.0f} c/k"
            f"  {flag}{mkt.gap_cop_kwh:>+5.0f}"
            f"  {loss:>12}"
        )
    if opt.total_loss_above_limit_cop < 0:
        blank()
        lines.append(f"  {'Pérdida total sobre límite:':45} {_mcop(opt.total_loss_above_limit_cop):>12}  🔴")

    # ── 2. Antes vs Después ───────────────────────────────────────────────────
    # Find the "después" month: the most critical (most negative balance)
    critical_snaps = [s for s in fwd.snapshots if s.balance_mwh < 0]
    cliff_snap = min(critical_snaps, key=lambda s: s.balance_mwh) if critical_snaps else (
        max(fwd.snapshots, key=lambda s: s.balance_mwh) if fwd.snapshots else None
    )

    section(f"2.  AHORA vs DESPUÉS  —  {month_name} → {cliff_snap.year}-{cliff_snap.month:02d}" if cliff_snap else "2.  AHORA vs DESPUÉS")

    now_bal   = opt.overall_balance_mwh
    now_rcov  = data.current_reg_cov
    now_nrcov = data.current_nr_cov

    if cliff_snap:
        cl_bal   = cliff_snap.balance_mwh
        cl_rcov  = cliff_snap.coverage_reg_pct
        cl_nrcov = cliff_snap.coverage_nr_pct
        cl_buy   = cliff_snap.bolsa_buy_mwh / 1_000

        COL = 27
        lines.append(f"  {'':─<{COL}}  {'':─<{COL}}")
        lines.append(f"  {'AHORA (' + month_name + ')':<{COL}}  {'DESPUÉS (' + f'{cliff_snap.year}-{cliff_snap.month:02d}' + ')':<{COL}}")
        lines.append(f"  {'':─<{COL}}  {'':─<{COL}}")

        def vs_row(label, now_val, cl_val, fmt):
            lines.append(f"  {label:<16} {fmt(now_val):<10}  {label:<16} {fmt(cl_val):<10}")

        lines.append(f"  {'Balance neto':<16} {_gwh(now_bal):<10}  {'Balance neto':<16} {_gwh(cl_bal):<10}  {_bal_icon(cl_bal)}")
        lines.append(f"  {'Bolsa compra':<16} {_gwh(buy_gwh * 1000):<10}  {'Bolsa compra':<16} {_gwh(cl_buy * 1000):<10}")
        lines.append(f"  {'Cob. Regulado':<16} {_pct(now_rcov):<10}  {'Cob. Regulado':<16} {_pct(cl_rcov):<10}  {_cov_icon(cl_rcov)}")
        lines.append(f"  {'Cob. No Reg.':<16} {_pct(now_nrcov):<10}  {'Cob. No Reg.':<16} {_pct(cl_nrcov):<10}  {_cov_icon(cl_nrcov)}")
        lines.append(f"  {'':─<{COL}}  {'':─<{COL}}")

        # Delta summary
        delta_bal  = cl_bal - now_bal
        delta_rcov = cl_rcov - now_rcov
        blank()
        lines.append(f"  Cambio en balance     : {_gwh(delta_bal)} ({'+' if delta_bal > 0 else ''}{delta_bal/1000:.1f} GWh)")
        lines.append(f"  Cambio cob. regulado  : {delta_rcov:+.1f} pp  ({now_rcov:.0f}% → {cl_rcov:.0f}%)")
        lines.append(f"  Bolsa compra adicional: {_gwh((cl_buy - buy_gwh) * 1000)}/mes más")

    # ── 3. Cobertura próximos 12 meses ────────────────────────────────────────
    section("3.  COBERTURA  —  PRÓXIMOS 12 MESES")

    HDR = f"  {'Mes':<9}  {'Regulado':>10}  {'':20}  {'No Reg.':>8}  {'':20}  {'Balance':>10}"
    lines.append(HDR)
    lines.append("  " + "─" * (W - 2))

    for r in data.coverage_rows:
        rcov  = r["reg_cov"]
        nrcov = r["nr_cov"]
        bal   = r["balance"]
        icon  = _bal_icon(bal)
        lines.append(
            f"  {r['period']:<9}"
            f"  {_pct(rcov):>6}  {_bar(rcov)}"
            f"  {_pct(nrcov):>6}  {_bar(nrcov)}"
            f"  {_gwh(bal):>10}  {icon}"
        )

    # ── 4. Alertas activas ────────────────────────────────────────────────────
    section(f"4.  ALERTAS ACTIVAS  —  {n_crit} críticas · {n_warn} advertencias")

    if not data.alert_report.alerts:
        lines.append("  🟢  Sin alertas activas.")
    else:
        for a in data.alert_report.alerts:
            lines.append(f"  {_sev_icon(a.severity)}  [{a.category.value.upper()}]  {_to_gwh(a.message)}")
            if a.detail:
                lines.append(f"       {_to_gwh(a.detail)}")

    # ── 5. Contratos urgentes ─────────────────────────────────────────────────
    cliff = cal.largest_cliff()
    section(f"5.  CONTRATOS A RENOVAR  —  {len(cal.all_events)} vencimientos en el horizonte")

    if cliff:
        lines.append(
            f"  Mayor brecha: {cliff.label}  →  "
            f"{_gwh(cliff.total_kwh_lost / 1_000)} perdidos  |  {_mcop(cliff.total_cost_lost_cop)}/mes"
        )
        blank()

    today = data.generated_at
    for m in cal.months_with_expiry():
        months_away = (m.year - today.year) * 12 + (m.month - today.month)
        urgency = "🔴 URGENTE" if months_away <= 3 else ("🟡 PRONTO " if months_away <= 6 else "📌        ")
        volume = _gwh(m.total_kwh_lost / 1_000)
        lines.append(f"  {urgency}  Gap en {m.label}  →  {volume}  ({_mcop(m.total_cost_lost_cop)}/mes)")
        for ev in sorted(m.events, key=lambda e: e.monthly_qty_kwh, reverse=True):
            if ev.monthly_qty_kwh == 0:
                continue
            lines.append(
                f"           {ev.sic_code}  {ev.contraparte:<6}  "
                f"{ev.market_type:<12}  {_gwh(ev.monthly_qty_kwh / 1_000)}  "
                f"@ {ev.price_cop_kwh:.0f} COP/kWh  (vence {ev.end_date.strftime('%Y-%m')})"
            )

    # ── 6. Acciones prioritarias ──────────────────────────────────────────────
    section("6.  ACCIONES PRIORITARIAS")

    # Acciones de curvas
    for action in opt.actions:
        lines.append(f"  {action}")

    # Renovaciones urgentes
    urgent = [m for m in cal.months_with_expiry()
              if (m.year - today.year) * 12 + (m.month - today.month) <= 3
              and m.total_kwh_lost > 0]
    if urgent:
        blank()
        lines.append("  Renovaciones inmediatas:")
        for m in urgent:
            for ev in sorted(m.events, key=lambda e: e.monthly_qty_kwh, reverse=True):
                if ev.monthly_qty_kwh == 0:
                    continue
                lines.append(
                    f"  🔴  Renovar {ev.contract_number} / {ev.contraparte}"
                    f"  ({ev.market_type})  {_gwh(ev.monthly_qty_kwh / 1_000)}/mes"
                    f"  —  vence {ev.end_date.strftime('%Y-%m')}"
                )

    # ── Footer ────────────────────────────────────────────────────────────────
    blank()
    div()
    lines.append(f"  Fuente: API Olibia Energy  |  {data.generated_at}  |  {data.version_name}")
    div()
    blank()

    return "\n".join(lines)
