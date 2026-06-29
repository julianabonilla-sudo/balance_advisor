"""Fetches all data for the advisory report and assembles it."""

from datetime import date

from src.api import OlibiaEnergy
from src.config import settings
from src.alerts.engine import build_month_snapshot
from src.curves.engine import run_curve_analysis

from .engine import build_advisory, BUY_THRESHOLD_PCT, SELL_THRESHOLD_PCT
from .builder import build_advisory_report


def run_advisor(
    year: int = None,
    month: int = None,
    version_name: str = None,
    horizon_months: int = 12,
) -> str:
    today = date.today()
    vname = version_name or settings.default_version_name

    with OlibiaEnergy() as olibia:
        # ── Resolve reference month ───────────────────────────────────────────
        if year is None or month is None:
            months = olibia.balance.available_months()["months"]
            past = [m for m in months if (m["year"], m["month"]) <= (today.year, today.month)]
            latest = (past or months)[0]
            year, month = latest["year"], latest["month"]

        try:
            ctx = olibia.balance.context(year, month)
            vname = ctx["version_names"][-1] if ctx.get("version_names") else vname
        except Exception:
            pass

        print(f"  Cargando mes actual: {year}-{month:02d} ({vname})…")
        dashboard     = olibia.balance.dashboard(year, month, vname)
        analysis      = olibia.balance.analysis(year, month, vname)
        income        = olibia.balance.income_statement(year, month, vname)
        bolsa_summary = olibia.balance.bolsa_summary(year, month, vname)

        # ── Current month price references ────────────────────────────────────
        print("  Calculando curvas y precios referencia…")
        opt = run_curve_analysis(
            year=year, month=month, version_name=vname,
            dashboard=dashboard, analysis=analysis,
            income=income, bolsa_summary=bolsa_summary,
        )
        bolsa_price = opt.regulado.bolsa_buy_price

        # Bolsa sell price → ceiling for contract buy recommendations
        # (buying below this price is always better than buying on the spot market)
        propio = bolsa_summary.get("propio", {})
        min_bolsa_price = propio.get("sell_price", 0) or bolsa_price

        # Weighted avg buy price of NR contracts → sell floor
        scatter = analysis.get("scatter_contracts", [])
        nr_contracts = [
            c for c in scatter
            if "NO" in c.get("market", "").upper()
        ]
        total_qty_nr = sum(c.get("qty", 0) for c in nr_contracts)
        if total_qty_nr > 0:
            avg_nr_buy_price = (
                sum(c.get("price", 0) * c.get("qty", 0) for c in nr_contracts)
                / total_qty_nr
            )
        else:
            avg_nr_buy_price = min_bolsa_price

        # ── Future months — fetch demand/contracts per market ─────────────────
        print(f"  Analizando horizonte {horizon_months} meses…")
        all_months = olibia.balance.available_months()["months"]
        future = sorted(
            [m for m in all_months if (m["year"], m["month"]) > (today.year, today.month)],
            key=lambda m: (m["year"], m["month"]),
        )[:horizon_months]

        future_data: list[dict] = []
        coverage_rows: list[dict] = []

        for m in future:
            y, mo = m["year"], m["month"]
            try:
                ctx = olibia.balance.context(y, mo)
                v = ctx["version_names"][-1] if ctx.get("version_names") else vname
                d = olibia.balance.dashboard(y, mo, v, with_projected_contracts=True)
                kpis = d.get("kpis", {})

                reg   = kpis.get("regulado", {})
                nr    = kpis.get("no_regulado", {})
                total = kpis.get("total", {})

                demand_reg    = reg.get("demand_mwh", 0)
                contracts_reg = reg.get("contracts_mwh", 0)
                demand_nr     = nr.get("demand_mwh", 0)
                contracts_nr  = nr.get("contracts_mwh", 0)
                balance_mwh   = total.get("balance_mwh", 0)

                future_data.append({
                    "year": y, "month": mo,
                    "demand_reg_mwh":    demand_reg,
                    "contracts_reg_mwh": contracts_reg,
                    "demand_nr_mwh":     demand_nr,
                    "contracts_nr_mwh":  contracts_nr,
                    "balance_mwh":       balance_mwh,
                })

                cov_reg = (contracts_reg / demand_reg * 100) if demand_reg > 0 else 0.0
                cov_nr  = (contracts_nr  / demand_nr  * 100) if demand_nr  > 0 else 0.0
                coverage_rows.append({
                    "period":  f"{y}-{mo:02d}",
                    "reg_cov": cov_reg,
                    "nr_cov":  cov_nr,
                    "balance": balance_mwh,
                })
            except Exception:
                continue

    print("  Generando reporte asesor…\n")

    advisory = build_advisory(
        year=year, month=month, version_name=vname,
        bolsa_price=bolsa_price,
        min_bolsa_price=min_bolsa_price,
        avg_nr_buy_price=avg_nr_buy_price,
        future_months_data=future_data,
        coverage_rows=coverage_rows,
    )

    return build_advisory_report(advisory, today)
