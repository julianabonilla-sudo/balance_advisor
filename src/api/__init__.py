from .client import OlibiaClient
from .balance import BalanceAPI
from .contracts import ContractsAPI


class OlibiaEnergy:
    def __init__(self):
        self._client = OlibiaClient()
        self.balance = BalanceAPI(self._client)
        self.contracts = ContractsAPI(self._client)

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
