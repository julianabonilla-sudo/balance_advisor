"""Formats the advisory report."""

from datetime import date

from .engine import AdvisoryReport, MonthAdvisory, MarketRec

W = 64


def _gwh(mwh_or_gwh: float, already_gwh: bool = True) -> str:
    v = mwh_or_gwh if already_gwh else mwh_or_gwh / 1_000
    return f"{v:.1f} GWh"


def _pct(v: float) -> str:
    return f"{v:.0f}%"


def _cop(v: float) -> str:
    return f"{v:.0f} COP/kWh"


def _cov_icon(pct: float) -> str:
    if pct < 70:   return "🔴"
    if pct < 80:   return "🟠"
    if pct < 100:  return "🟡"
    return "🟢"


def _bar(pct: float, width: int = 18, cap: int = 200) -> str:
    filled = min(int(pct / cap * width), width)
    return "|" + "█" * filled + "░" * (width - filled) + "|"


def _bal_icon(gwh: float) -> str:
    if gwh < -5:  return "🔴"
    if gwh < 0:   return "🟠"
    return "🟢"


def _group_consecutive(advisories: list[MonthAdvisory], market: str, action: str):
    """Group consecutive months that share the same market+action into runs."""
    filtered = [(a, next((r for r in a.recs if r.market == market and r.action == action), None))
                for a in advisories]
    filtered = [(a, r) for a, r in filtered if r is not None]

    groups = []
    current = []
    for a, r in filtered:
        if current:
            prev_a, _ = current[-1]
            if (a.year * 12 + a.month) - (prev_a.year * 12 + prev_a.month) == 1:
                current.append((a, r))
            else:
                groups.append(current)
                current = [(a, r)]
        else:
            current = [(a, r)]
    if current:
        groups.append(current)
    return groups


def _month_label(year: int, month: int) -> str:
    return date(year, month, 1).strftime("%b %Y")


def build_advisory_report(report: AdvisoryReport, today: date = None) -> str:
    today = today or date.today()
    lines: list[str] = []

    def div(ch="═"):
        lines.append(ch * W)

    def blank():
        lines.append("")

    def section(title: str):
        blank()
        lines.append("▌ " + title)
        lines.append("  " + "─" * (W - 2))

    month_name = date(report.year, report.month, 1).strftime("%b %Y").upper()

    # ── Header ────────────────────────────────────────────────────────────────
    div()
    lines.append("⚡ ENERGY BALANCE ADVISOR — REPORTE ASESOR")
    lines.append(f"   {month_name} ({report.version_name})  |  Generado: {today}")
    div()
    blank()
    lines.append(f"  Precio bolsa hoy  : {_cop(report.bolsa_price)}  (promedio mes actual)")
    lines.append(f"  Precio venta bolsa: {_cop(report.min_bolsa_price)}  (precio venta en bolsa — techo para compras)")
    lines.append(f"  Prom. compra NR   : {_cop(report.avg_nr_buy_price)}  (piso para ventas no regulado)")

    # ── 1. Cobertura 12 meses ─────────────────────────────────────────────────
    section("1.  COBERTURA — PRÓXIMOS 12 MESES")
    lines.append(f"  {'Mes':<9}  {'Regulado':>8}  {'':18}  {'No Reg.':>8}  {'':18}  {'Balance':>9}")
    lines.append("  " + "─" * (W - 2))

    for r in report.coverage_rows:
        rcov  = r["reg_cov"]
        nrcov = r["nr_cov"]
        bal   = r["balance"]
        bal_gwh = bal / 1_000   # balance stored as MWh in coverage_rows
        lines.append(
            f"  {r['period']:<9}"
            f"  {_pct(rcov):>6}  {_bar(rcov)}"
            f"  {_pct(nrcov):>6}  {_bar(nrcov)}"
            f"  {_gwh(bal_gwh):>8}  {_bal_icon(bal_gwh)}"
        )

    # ── 2. Recomendaciones de compra ──────────────────────────────────────────
    buy_months = report.months_needing_buy
    section(f"2.  RECOMENDACIONES DE COMPRA  ({len(buy_months)} meses con déficit)")

    if not buy_months:
        lines.append("  🟢  Sin déficit de cobertura en el horizonte.")
    else:
        for market, label_mkt in [("regulado", "Regulado"), ("no_regulado", "No Regulado")]:
            groups = _group_consecutive(report.advisories, market, "COMPRA")
            if not groups:
                continue

            for group in groups:
                months_in_group = [a for a, _ in group]
                recs_in_group   = [r for _, r in group]

                first = months_in_group[0]
                last  = months_in_group[-1]
                avg_gap     = sum(r.gap_gwh for r in recs_in_group) / len(recs_in_group)
                max_gap     = max(r.gap_gwh for r in recs_in_group)
                price_ref   = recs_in_group[0].suggested_price_cop_kwh   # min bolsa
                bolsa_price = recs_in_group[0].bolsa_price_cop_kwh
                savings     = bolsa_price - price_ref

                if first is last:
                    period = _month_label(first.year, first.month)
                else:
                    period = f"{_month_label(first.year, first.month)} → {_month_label(last.year, last.month)}"

                blank()
                lines.append(f"  📌  {label_mkt.upper()}  ·  {period}  ({len(group)} mes{'es' if len(group) > 1 else ''})")
                lines.append(f"  {'':─<{W - 4}}")
                lines.append(f"    Déficit promedio   : {avg_gap:.1f} GWh/mes")
                lines.append(f"    Déficit máximo     : {max_gap:.1f} GWh/mes")
                lines.append(f"    Precio sugerido    : < {_cop(price_ref)}  (precio venta en bolsa)")
                lines.append(f"    Precio bolsa hoy   : {_cop(bolsa_price)}")
                lines.append(f"    Ahorro vs bolsa    : {savings:.0f} COP/kWh")
                blank()
                lines.append(f"    Acción: buscar contratos de compra en mercado {label_mkt}")
                lines.append(f"    a precio < {_cop(price_ref)}  (precio venta en bolsa).")
                lines.append(f"    Comprar por debajo garantiza mejor precio que la bolsa en cualquier escenario.")

                # Monthly detail if group has multiple months
                if len(group) > 1:
                    blank()
                    lines.append(f"    {'Mes':<10}  {'Cobertura':>10}  {'Déficit':>10}")
                    lines.append(f"    {'':─<34}")
                    for a, r in group:
                        lines.append(
                            f"    {_month_label(a.year, a.month):<10}"
                            f"  {_pct(r.coverage_pct):>10}"
                            f"  {_gwh(r.gap_gwh):>10}"
                        )

    # ── 3. Recomendaciones de venta ───────────────────────────────────────────
    sell_months = report.months_needing_sell
    section(f"3.  RECOMENDACIONES DE VENTA  ({len(sell_months)} meses con excedente)")

    if not sell_months:
        lines.append("  🟢  Sin excedente relevante en el horizonte.")
    else:
        for market, label_mkt in [("regulado", "Regulado"), ("no_regulado", "No Regulado")]:
            groups = _group_consecutive(report.advisories, market, "VENTA")
            if not groups:
                continue

            for group in groups:
                months_in_group = [a for a, _ in group]
                recs_in_group   = [r for _, r in group]

                first = months_in_group[0]
                last  = months_in_group[-1]
                avg_surplus = sum(r.gap_gwh for r in recs_in_group) / len(recs_in_group)
                max_surplus = max(r.gap_gwh for r in recs_in_group)
                price_ref   = recs_in_group[0].suggested_price_cop_kwh  # avg NR buy price
                bolsa_price = recs_in_group[0].bolsa_price_cop_kwh

                if first is last:
                    period = _month_label(first.year, first.month)
                else:
                    period = f"{_month_label(first.year, first.month)} → {_month_label(last.year, last.month)}"

                blank()
                lines.append(f"  💰  {label_mkt.upper()}  ·  {period}  ({len(group)} mes{'es' if len(group) > 1 else ''})")
                lines.append(f"  {'':─<{W - 4}}")
                lines.append(f"    Excedente promedio : {avg_surplus:.1f} GWh/mes")
                lines.append(f"    Excedente máximo   : {max_surplus:.1f} GWh/mes")
                lines.append(f"    Precio sugerido    : > {_cop(price_ref)}  (prom. compra portafolio NR)")
                lines.append(f"    Precio bolsa hoy   : {_cop(bolsa_price)}")
                blank()
                lines.append(f"    Acción: vender excedente en mercado No Regulado")
                lines.append(f"    a precio > {_cop(price_ref)}  (promedio ponderado de compra NR).")
                lines.append(f"    Opciones:")
                lines.append(f"    → Bolsa spot     : {_cop(bolsa_price)}  (precio actual)")
                lines.append(f"    → Bilateral      : negociar a precio > {_cop(price_ref)}  para asegurar margen")

                if len(group) > 1:
                    blank()
                    lines.append(f"    {'Mes':<10}  {'Cobertura':>10}  {'Excedente':>10}")
                    lines.append(f"    {'':─<34}")
                    for a, r in group:
                        lines.append(
                            f"    {_month_label(a.year, a.month):<10}"
                            f"  {_pct(r.coverage_pct):>10}"
                            f"  {_gwh(r.gap_gwh):>10}"
                        )

    # ── Footer ────────────────────────────────────────────────────────────────
    blank()
    div()
    lines.append(f"  Fuente: API Olibia Energy  |  {today}  |  {report.version_name}")
    div()
    blank()

    return "\n".join(lines)
