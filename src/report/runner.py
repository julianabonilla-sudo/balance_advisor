"""Fetches all data needed for the executive report and assembles it."""

from datetime import date

from src.api import OlibiaEnergy
from src.config import settings
from src.alerts.engine import run_alerts, build_month_snapshot, check_forward_trend
from src.curves.engine import run_curve_analysis
from src.contracts.expiry import build_expiry_calendar

from .builder import ReportData, build_report


def run_report(
    year: int = None,
    month: int = None,
    version_name: str = None,
    horizon_months: int = 18,
) -> str:
    """Fetch all data, run every analysis, return the formatted report string."""
    today = date.today()
    vname = version_name or settings.default_version_name

    with OlibiaEnergy() as olibia:
        # ── Resolve reference month ────────────────────────────────────────────
        if year is None or month is None:
            months = olibia.balance.available_months()["months"]
            # Most recent month with actual data (≤ today)
            past = [m for m in months if (m["year"], m["month"]) <= (today.year, today.month)]
            if not past:
                past = months  # fallback: use the most recent available
            latest = past[0]
            year, month = latest["year"], latest["month"]

        # Resolve version_name from context
        try:
            ctx = olibia.balance.context(year, month)
            vname = ctx["version_names"][-1] if ctx.get("version_names") else vname
        except Exception:
            pass

        print(f"  Cargando datos: {year}-{month:02d} ({vname})…")

        # ── Fetch base data (reused across analyses) ───────────────────────────
        dashboard     = olibia.balance.dashboard(year, month, vname)
        matrix        = olibia.balance.matrix_hourly(year, month, vname)
        analysis      = olibia.balance.analysis(year, month, vname)
        income        = olibia.balance.income_statement(year, month, vname)
        bolsa_summary = olibia.balance.bolsa_summary(year, month, vname)
        contracts_raw = olibia.contracts.list(limit=500)

        print(f"  Calculando alertas del mes…")
        alert_report = run_alerts(
            year=year, month=month, version_name=vname,
            dashboard=dashboard, matrix=matrix, analysis=analysis,
        )

        print(f"  Calculando curvas y precio límite…")
        opt_result = run_curve_analysis(
            year=year, month=month, version_name=vname,
            dashboard=dashboard, analysis=analysis,
            income=income, bolsa_summary=bolsa_summary,
        )

        print(f"  Calculando vencimientos de contratos…")
        expiry_cal = build_expiry_calendar(
            contracts_list=contracts_raw,
            scatter_contracts=analysis.get("scatter_contracts", []),
            reference_year=year,
            reference_month=month,
            horizon_months=horizon_months,
        )

        print(f"  Analizando tendencia {horizon_months} meses…")
        all_months = olibia.balance.available_months()["months"]
        future_months = sorted(
            [m for m in all_months if (m["year"], m["month"]) > (today.year, today.month)],
            key=lambda m: (m["year"], m["month"]),
        )[:horizon_months]

        snapshots = []
        for m in future_months:
            y, mo = m["year"], m["month"]
            try:
                ctx = olibia.balance.context(y, mo)
                v = ctx["version_names"][-1] if ctx.get("version_names") else vname
                d = olibia.balance.dashboard(y, mo, v, with_projected_contracts=True)
                snapshots.append(build_month_snapshot(y, mo, v, d))
            except Exception:
                continue

        forward_report = check_forward_trend(snapshots)

        print(f"  Construyendo tabla de cobertura…")
        coverage_rows = []
        for snap in snapshots[:12]:
            coverage_rows.append({
                "period":    f"{snap.year}-{snap.month:02d}",
                "reg_cov":   snap.coverage_reg_pct,
                "nr_cov":    snap.coverage_nr_pct,
                "balance":   snap.balance_mwh,
            })

        # Coverage for the reference month itself (from dashboard kpis)
        kpis = dashboard.get("kpis", {})
        def _cov(market_key: str) -> float:
            d = kpis.get(market_key, {})
            demand = d.get("demand_mwh", 0)
            return (d.get("contracts_mwh", 0) / demand * 100) if demand > 0 else 0.0

        current_reg_cov = _cov("regulado")
        current_nr_cov  = _cov("no_regulado")

    print(f"  Generando reporte…\n")

    data = ReportData(
        generated_at=today,
        year=year,
        month=month,
        version_name=vname,
        alert_report=alert_report,
        forward_report=forward_report,
        opt_result=opt_result,
        expiry_calendar=expiry_cal,
        coverage_rows=coverage_rows,
        current_reg_cov=current_reg_cov,
        current_nr_cov=current_nr_cov,
    )

    return build_report(data)
