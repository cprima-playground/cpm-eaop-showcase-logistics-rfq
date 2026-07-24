"""Clients for TMS/Rate/FX -- same shape as rfq_common.masterdata_client.MasterdataClient
(raw httpx, get/list/404->None, fail-closed on network error). The dashboard is
the first thing in RfQ to fan out to more than one peer system, so this copies
the sanctioned pattern a fourth time rather than inventing an abstraction over it.
"""

from __future__ import annotations

import os

import httpx


class TmsUnavailableError(RuntimeError):
    pass


class RateUnavailableError(RuntimeError):
    pass


class FxUnavailableError(RuntimeError):
    pass


class QmsUnavailableError(RuntimeError):
    pass


class TmsClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 5.0):
        self._base_url = base_url or os.environ.get("TMS_URL", "http://127.0.0.1:8004")
        self._api_key = api_key
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        return self._base_url

    def _get(self, path: str) -> dict | list | None:
        try:
            r = httpx.get(
                f"{self._base_url}{path}",
                headers={"X-API-Key": self._api_key or ""},
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise TmsUnavailableError(f"TMS unreachable at {self._base_url}: {exc}") from exc
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def list_routes(self) -> list[dict]:
        return self._get("/routes") or []

    def get_route(self, route_id: str) -> dict | None:
        return self._get(f"/routes/{route_id}")

    def get_availability(self, route_id: str) -> dict | None:
        return self._get(f"/routes/{route_id}/availability")

    def stats(self) -> dict:
        return self._get("/admin/stats") or {}


class RateClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 5.0):
        self._base_url = base_url or os.environ.get("RATE_URL", "http://127.0.0.1:8005")
        self._api_key = api_key
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        return self._base_url

    def _get(self, path: str) -> dict | list | None:
        try:
            r = httpx.get(
                f"{self._base_url}{path}",
                headers={"X-API-Key": self._api_key or ""},
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise RateUnavailableError(f"Rate unreachable at {self._base_url}: {exc}") from exc
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def list_rates(self) -> list[dict]:
        return self._get("/rates") or []

    def get_rate(self, route_id: str) -> dict | None:
        return self._get(f"/rates/{route_id}")

    def stats(self) -> dict:
        return self._get("/admin/stats") or {}


class FxClient:
    """Point lookups by currency pair, plus a generated 30-day history for
    charting (mock-fx's generator.py -- deterministic, seeded, never static
    fixture files beyond the 2 real anchor snapshots)."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 5.0):
        self._base_url = base_url or os.environ.get("FX_URL", "http://127.0.0.1:8001")
        self._api_key = api_key
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        return self._base_url

    def _get(self, path: str) -> dict | list | None:
        try:
            r = httpx.get(
                f"{self._base_url}{path}",
                headers={"X-API-Key": self._api_key or ""},
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise FxUnavailableError(f"FX unreachable at {self._base_url}: {exc}") from exc
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def list_rates(self) -> list[dict]:
        """The latest rate for every known pair -- the overview page (list-then-
        detail, matches TmsClient.list_routes/RateClient.list_rates)."""
        return self._get("/exchange-rates") or []

    def get_rate(self, base: str, quote: str) -> dict | None:
        return self._get(f"/exchange-rates/{base}/{quote}")

    def get_rate_history(self, base: str, quote: str, days: int = 30) -> list[dict]:
        return self._get(f"/exchange-rates/{base}/{quote}/history?days={days}") or []

    def stats(self) -> dict:
        return self._get("/admin/stats") or {}


class QmsClient:
    """mock-qms is a minimal skeleton today (no business routes, no APIKEY --
    see src/mock-qms/mock_qms/api.py's docstring): there's no authenticated
    business call to probe yet. `probe()` hits /openapi.json instead -- proves
    the real FastAPI app booted and its schema loaded, not just that SOME
    process answers on the port."""

    def __init__(self, base_url: str | None = None, timeout: float = 5.0):
        self._base_url = base_url or os.environ.get("QMS_URL", "http://127.0.0.1:8007")
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        return self._base_url

    def probe(self) -> dict:
        try:
            r = httpx.get(f"{self._base_url}/openapi.json", timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise QmsUnavailableError(f"QMS unreachable at {self._base_url}: {exc}") from exc
        r.raise_for_status()
        return r.json()
