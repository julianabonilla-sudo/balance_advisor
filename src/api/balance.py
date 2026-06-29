from .client import OlibiaClient


class BalanceAPI:
    def __init__(self, client: OlibiaClient):
        self._c = client

    def available_months(self) -> dict:
        return self._c.get("/balance/available-months")

    def context(self, year: int, month: int) -> dict:
        return self._c.get("/balance/context", {"year": year, "month": month})

    def dashboard(
        self,
        year: int,
        month: int,
        version_name: str,
        ptb_version_file: str = None,
        with_projected_contracts: bool = False,
    ) -> dict:
        params = {
            "year": year,
            "month": month,
            "version_name": version_name,
            "with_projected_contracts": str(with_projected_contracts).lower(),
        }
        if ptb_version_file:
            params["ptb_version_file"] = ptb_version_file
        return self._c.get("/balance/dashboard", params)

    def matrix_hourly(
        self,
        year: int,
        month: int,
        version_name: str,
        ptb_version_file: str = None,
        with_projected_contracts: bool = False,
    ) -> dict:
        params = {
            "year": year,
            "month": month,
            "version_name": version_name,
            "with_projected_contracts": str(with_projected_contracts).lower(),
        }
        if ptb_version_file:
            params["ptb_version_file"] = ptb_version_file
        return self._c.get("/balance/matrix-hourly", params)

    def analysis(
        self,
        year: int,
        month: int,
        version_name: str,
        ptb_version_file: str = None,
        with_projected_contracts: bool = False,
    ) -> dict:
        params = {
            "year": year,
            "month": month,
            "version_name": version_name,
            "with_projected_contracts": str(with_projected_contracts).lower(),
        }
        if ptb_version_file:
            params["ptb_version_file"] = ptb_version_file
        return self._c.get("/balance/results/analysis", params)

    def income_statement(
        self,
        year: int,
        month: int,
        version_name: str,
        ptb_version_file: str = None,
        with_projected_contracts: bool = False,
    ) -> dict:
        params = {
            "year": year,
            "month": month,
            "version_name": version_name,
            "with_projected_contracts": str(with_projected_contracts).lower(),
        }
        if ptb_version_file:
            params["ptb_version_file"] = ptb_version_file
        return self._c.get("/balance/results/income-statement", params)

    def bolsa_summary(
        self,
        year: int,
        month: int,
        version_name: str,
        ptb_version_file: str = None,
        with_projected_contracts: bool = False,
    ) -> dict:
        params = {
            "year": year,
            "month": month,
            "version_name": version_name,
            "with_projected_contracts": str(with_projected_contracts).lower(),
        }
        if ptb_version_file:
            params["ptb_version_file"] = ptb_version_file
        return self._c.get("/balance/results/bolsa-summary", params)

    def contracts(self, year: int, month: int, version_name: str) -> dict:
        return self._c.get("/balance/contracts", {
            "year": year, "month": month, "version_name": version_name,
        })

    def cross(
        self, year: int, month: int, version_name: str, ptb_version_file: str = None
    ) -> dict:
        params = {"year": year, "month": month, "version_name": version_name}
        if ptb_version_file:
            params["ptb_version_file"] = ptb_version_file
        return self._c.get("/balance/cross", params)

    def day(self, file_date: str, version_name: str, ptb_version_file: str = None) -> dict:
        params = {"file_date": file_date, "version_name": version_name}
        if ptb_version_file:
            params["ptb_version_file"] = ptb_version_file
        return self._c.get("/balance/day", params)

    def forecast_range(self) -> dict:
        return self._c.get("/balance/forecast-range")

    def ipp_summary(self) -> dict:
        return self._c.get("/balance/ipp-summary")

    def reconciliation(
        self, year: int, month: int, version_name: str, ptb_version_file: str = None
    ) -> dict:
        params = {"year": year, "month": month, "version_name": version_name}
        if ptb_version_file:
            params["ptb_version_file"] = ptb_version_file
        return self._c.get("/balance/reconciliation", params)
