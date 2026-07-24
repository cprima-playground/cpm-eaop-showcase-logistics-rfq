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


class TmsClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 5.0):
        self._base_url = base_url or os.environ.get("TMS_URL", "http://localhost:8004")
        self._api_key = api_key
        self._timeout = timeout

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


class RateClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 5.0):
        self._base_url = base_url or os.environ.get("RATE_URL", "http://localhost:8005")
        self._api_key = api_key
        self._timeout = timeout

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


class FxClient:
    """No bulk list endpoint on mock-fx (by design -- see its README) --
    only point lookups by currency pair."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 5.0):
        self._base_url = base_url or os.environ.get("FX_URL", "http://localhost:8001")
        self._api_key = api_key
        self._timeout = timeout

    def _get(self, path: str) -> dict | None:
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

    def get_rate(self, base: str, quote: str) -> dict | None:
        return self._get(f"/exchange-rates/{base}/{quote}")
