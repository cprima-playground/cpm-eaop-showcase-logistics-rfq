"""Cross-system clients QMS's real pricing pipeline needs -- same raw-httpx
pattern as every other client in this codebase (rfq_common.masterdata_client,
ops_dashboard/clients.py). QMS is the first system to call BOTH mock-rate
and mock-fx for real (the x-consults already declared on POST .../price) --
these are QMS-owned copies, not shared, matching the established
per-system-client convention (ops_dashboard/clients.py's own docstring)."""

from __future__ import annotations

import os

import httpx


class RateUnavailableError(RuntimeError):
    pass


class FxUnavailableError(RuntimeError):
    pass


class TmsUnavailableError(RuntimeError):
    pass


class RateClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 5.0):
        self._base_url = base_url or os.environ.get("RATE_URL", "http://127.0.0.1:8005")
        self._api_key = api_key
        self._timeout = timeout

    def get_rate(self, route_id: str) -> dict | None:
        try:
            r = httpx.get(
                f"{self._base_url}/rates/{route_id}",
                headers={"X-API-Key": self._api_key or ""},
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise RateUnavailableError(f"Rate unreachable at {self._base_url}: {exc}") from exc
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()


class FxClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 5.0):
        self._base_url = base_url or os.environ.get("FX_URL", "http://127.0.0.1:8001")
        self._api_key = api_key
        self._timeout = timeout

    def convert(self, amount: str, from_currency: str, to_currency: str) -> dict:
        """GET /convert -- mock-fx is the currency-conversion authority
        (correctly rounded per the target currency's minor_unit)."""
        try:
            r = httpx.get(
                f"{self._base_url}/convert",
                params={"amount": amount, "from_currency": from_currency, "to_currency": to_currency},
                headers={"X-API-Key": self._api_key or ""},
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise FxUnavailableError(f"FX unreachable at {self._base_url}: {exc}") from exc
        r.raise_for_status()
        return r.json()


class TmsClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 5.0):
        self._base_url = base_url or os.environ.get("TMS_URL", "http://127.0.0.1:8004")
        self._api_key = api_key
        self._timeout = timeout

    def get_route_state(self, route_id: str) -> dict | None:
        """GET /routes/{id}/availability -- TMS is the sole authority on
        route executability; QMS asks for its current truth, not a cached
        availability field."""
        try:
            r = httpx.get(
                f"{self._base_url}/routes/{route_id}/availability",
                headers={"X-API-Key": self._api_key or ""},
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise TmsUnavailableError(f"TMS unreachable at {self._base_url}: {exc}") from exc
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
