import httpx
from src.config import settings


class OlibiaClient:
    def __init__(self):
        self._http = httpx.Client(
            base_url=settings.olibia_base_url,
            headers={
                "Api-key": settings.olibia_api_key,
                "X-User-Email": settings.olibia_user_email,
                "X-User-ID": settings.olibia_user_id,
            },
            timeout=30.0,
        )

    def get(self, path: str, params: dict = None) -> dict:
        response = self._http.get(path, params=params)
        response.raise_for_status()
        return response.json()

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
