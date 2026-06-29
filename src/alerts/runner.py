"""Alert runner — fetches live data and executes the full alert pipeline."""

from datetime import date

from src.api import OlibiaEnergy
from src.config import settings
from .engine import (
    AlertConfig,
    AlertReport,
    ForwardTrendReport,
    MonthSnapshot,
    build_month_snapshot,
    check_forward_trend,
    run_alerts,
)


def run_monthly_alerts(
    year: int,
    month: int,
    version_name: str = None,
    config: AlertConfig = None,
) -> AlertReport:
    """Fetch data for the given month and run all alert checks."""
    if version_name is None:
        version_name = settings.default_version_name

    with OlibiaEnergy() as olibia:
        dashboard = olibia.balance.dashboard(year, month, version_name)
        matrix = olibia.balance.matrix_hourly(year, month, version_name)
        analysis = olibia.balance.analysis(year, month, version_name)

    return run_alerts(
        year=year,
        month=month,
        version_name=version_name,
        dashboard=dashboard,
        matrix=matrix,
        analysis=analysis,
        config=config,
    )


def run_current_month_alerts(config: AlertConfig = None) -> AlertReport:
    """Detect the most recent month with data and run alerts on it."""
    with OlibiaEnergy() as olibia:
        months = olibia.balance.available_months()
        latest = months["months"][0]
        year, month = latest["year"], latest["month"]

        ctx = olibia.balance.context(year, month)
        version_name = ctx["version_names"][-1]

        dashboard = olibia.balance.dashboard(year, month, version_name)
        matrix = olibia.balance.matrix_hourly(year, month, version_name)
        analysis = olibia.balance.analysis(year, month, version_name)

    return run_alerts(
        year=year,
        month=month,
        version_name=version_name,
        dashboard=dashboard,
        matrix=matrix,
        analysis=analysis,
        config=config,
    )


def run_forward_trend_alerts(
    horizon_months: int = 12,
    config: AlertConfig = None,
    version_name: str = None,
) -> ForwardTrendReport:
    """Fetch the next N future months and check for worsening trends.

    Only months strictly after today are considered future. Months are
    collected in chronological order (oldest first) for delta comparisons.
    """
    if version_name is None:
        version_name = settings.default_version_name

    today = date.today()

    with OlibiaEnergy() as olibia:
        all_months = olibia.balance.available_months()["months"]

        # Keep only future months, oldest first
        future = sorted(
            [
                m for m in all_months
                if (m["year"], m["month"]) > (today.year, today.month)
            ],
            key=lambda m: (m["year"], m["month"]),
        )[:horizon_months]

        snapshots: list[MonthSnapshot] = []
        for m in future:
            y, mo = m["year"], m["month"]
            # Try to get version from context; fall back to configured default
            try:
                ctx = olibia.balance.context(y, mo)
                vname = ctx["version_names"][-1] if ctx.get("version_names") else version_name
            except Exception:
                vname = version_name

            try:
                dashboard = olibia.balance.dashboard(y, mo, vname, with_projected_contracts=True)
                snapshots.append(build_month_snapshot(y, mo, vname, dashboard))
            except Exception:
                # Skip months that fail (no data loaded yet)
                continue

    return check_forward_trend(snapshots, config)
