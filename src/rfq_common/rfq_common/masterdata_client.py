"""Client for the masterdata source (ADR-010) -- the ONLY sanctioned way another
system consumes masterdata: a real API call, never reading masterdata's fixture
files directly and never duplicating the data. Same raw-httpx shape as
pdp.client.PDPClient / secrets.vault.VaultReader.
"""

from __future__ import annotations

import os

import httpx


class MasterdataUnavailableError(RuntimeError):
    pass


class MasterdataClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 5.0):
        self._base_url = base_url or os.environ.get("MASTERDATA_URL", "http://localhost:8003")
        self._api_key = api_key
        self._timeout = timeout

    def get(self, domain: str, code: str) -> dict | None:
        try:
            r = httpx.get(
                f"{self._base_url}/{domain}/{code}",
                headers={"X-API-Key": self._api_key or ""},
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise MasterdataUnavailableError(f"masterdata unreachable at {self._base_url}: {exc}") from exc
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def list(self, domain: str) -> list[dict]:
        try:
            r = httpx.get(
                f"{self._base_url}/{domain}",
                headers={"X-API-Key": self._api_key or ""},
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise MasterdataUnavailableError(f"masterdata unreachable at {self._base_url}: {exc}") from exc
        r.raise_for_status()
        return r.json()

    def exists(self, domain: str, code: str) -> bool:
        return self.get(domain, code) is not None
