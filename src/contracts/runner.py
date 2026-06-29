"""Runner — fetches live data and builds the expiry calendar."""

from src.api import OlibiaEnergy
from src.config import settings
from .expiry import ExpiryCalendar, build_expiry_calendar


def run_expiry_analysis(
    reference_year: int,
    reference_month: int,
    version_name: str = None,
    horizon_months: int = 18,
) -> ExpiryCalendar:
    if version_name is None:
        version_name = settings.default_version_name

    with OlibiaEnergy() as olibia:
        contracts_list = olibia.contracts.list(limit=500)
        analysis = olibia.balance.analysis(reference_year, reference_month, version_name)

    scatter = analysis.get("scatter_contracts", [])

    return build_expiry_calendar(
        contracts_list=contracts_list,
        scatter_contracts=scatter,
        reference_year=reference_year,
        reference_month=reference_month,
        horizon_months=horizon_months,
    )
