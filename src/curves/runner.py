"""Curve analysis runner — fetches live data and executes the curve engine."""

from src.api import OlibiaEnergy
from src.config import settings
from .engine import OptimizationResult, run_curve_analysis


def run_curves(
    year: int,
    month: int,
    version_name: str = None,
    margin_pct: float = 0.0,
) -> OptimizationResult:
    """Fetch all required data and run the full curve + price-limit analysis."""
    if version_name is None:
        version_name = settings.default_version_name

    with OlibiaEnergy() as olibia:
        dashboard = olibia.balance.dashboard(year, month, version_name)
        analysis = olibia.balance.analysis(year, month, version_name)
        income = olibia.balance.income_statement(year, month, version_name)
        bolsa_summary = olibia.balance.bolsa_summary(year, month, version_name)

    return run_curve_analysis(
        year=year,
        month=month,
        version_name=version_name,
        dashboard=dashboard,
        analysis=analysis,
        income=income,
        bolsa_summary=bolsa_summary,
        margin_pct=margin_pct,
    )
