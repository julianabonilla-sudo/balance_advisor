from .client import OlibiaClient


class ContractsAPI:
    def __init__(self, client: OlibiaClient):
        self._c = client

    def list(self, limit: int = 100, offset: int = 0) -> dict:
        return self._c.get("/contracts", {"limit": limit, "offset": offset})

    def get(self, contract_id: str) -> dict:
        return self._c.get(f"/contracts/{contract_id}")

    def hourly(
        self,
        from_date: str = None,
        to_date: str = None,
        day_type: str = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        params = {"limit": limit, "offset": offset}
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date
        if day_type:
            params["day_type"] = day_type
        return self._c.get("/contracts/hourly", params)

    def monthly(self, day_type: str = None, limit: int = 100, offset: int = 0) -> dict:
        params = {"limit": limit, "offset": offset}
        if day_type:
            params["day_type"] = day_type
        return self._c.get("/contracts/monthly", params)

    def dashboard(
        self,
        from_date: str,
        to_date: str,
        market: str = None,
        operation_type: str = None,
        day_type: str = None,
        is_projected: bool = None,
    ) -> dict:
        params = {"from_date": from_date, "to_date": to_date}
        if market:
            params["market"] = market
        if operation_type:
            params["operation_type"] = operation_type
        if day_type:
            params["day_type"] = day_type
        if is_projected is not None:
            params["is_projected"] = str(is_projected).lower()
        return self._c.get("/contracts/analytics/dashboard", params)

    def dashboard_totalizado(
        self,
        from_date: str,
        to_date: str,
        market: str = None,
        is_projected: bool = None,
    ) -> dict:
        params = {"from_date": from_date, "to_date": to_date}
        if market:
            params["market"] = market
        if is_projected is not None:
            params["is_projected"] = str(is_projected).lower()
        return self._c.get("/contracts/analytics/dashboard-totalizado", params)

    def inventory_aggregated(
        self,
        from_date: str,
        to_date: str,
        market: str = None,
        day_type: str = None,
        price_type: str = None,
        is_projected: bool = None,
    ) -> dict:
        params = {"from_date": from_date, "to_date": to_date}
        if market:
            params["market"] = market
        if day_type:
            params["day_type"] = day_type
        if price_type:
            params["price_type"] = price_type
        if is_projected is not None:
            params["is_projected"] = str(is_projected).lower()
        return self._c.get("/contracts/analytics/inventory-aggregated", params)

    def inventory_total(
        self,
        from_date: str,
        to_date: str,
        market: str = None,
        day_type: str = None,
        price_type: str = None,
        is_projected: bool = None,
    ) -> dict:
        params = {"from_date": from_date, "to_date": to_date}
        if market:
            params["market"] = market
        if day_type:
            params["day_type"] = day_type
        if price_type:
            params["price_type"] = price_type
        if is_projected is not None:
            params["is_projected"] = str(is_projected).lower()
        return self._c.get("/contracts/analytics/inventory-total", params)

    def matrix_summary(
        self,
        from_date: str,
        to_date: str,
        day_type: str = None,
        price_type: str = None,
        is_projected: bool = None,
    ) -> dict:
        params = {"from_date": from_date, "to_date": to_date}
        if day_type:
            params["day_type"] = day_type
        if price_type:
            params["price_type"] = price_type
        if is_projected is not None:
            params["is_projected"] = str(is_projected).lower()
        return self._c.get("/contracts/analytics/matrix-summary", params)

    def contract_schedule(
        self,
        contract_id: str,
        from_date: str,
        to_date: str,
        market: str = None,
        day_type: str = None,
        price_type: str = None,
        is_projected: bool = None,
    ) -> dict:
        params = {"from_date": from_date, "to_date": to_date}
        if market:
            params["market"] = market
        if day_type:
            params["day_type"] = day_type
        if price_type:
            params["price_type"] = price_type
        if is_projected is not None:
            params["is_projected"] = str(is_projected).lower()
        return self._c.get(f"/contracts/{contract_id}/analytics/schedule", params)

    def contract_hourly(
        self,
        contract_id: str,
        from_date: str = None,
        to_date: str = None,
        day_type: str = None,
    ) -> dict:
        params = {}
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date
        if day_type:
            params["day_type"] = day_type
        return self._c.get(f"/contracts/{contract_id}/hourly", params)

    def contract_monthly(self, contract_id: str, day_type: str = None) -> dict:
        params = {}
        if day_type:
            params["day_type"] = day_type
        return self._c.get(f"/contracts/{contract_id}/monthly", params)
