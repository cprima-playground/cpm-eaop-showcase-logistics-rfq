from __future__ import annotations

import pytest

from geo_api.masterdata import LocodeNotFoundError, resolve_locode


class _FakeMasterdataClient:
    def __init__(self, rows: dict[str, dict]):
        self._rows = rows
        self.calls: list[str] = []

    def get(self, domain: str, code: str):
        assert domain == "locations"
        self.calls.append(code)
        return self._rows.get(code)


def test_resolves_a_known_locode():
    client = _FakeMasterdataClient({"CNSHA": {"lon": 121.5, "lat": 31.2}})
    coord = resolve_locode(client, "CNSHA", {})
    assert coord == (121.5, 31.2)


def test_raises_for_an_unknown_locode():
    client = _FakeMasterdataClient({})
    with pytest.raises(LocodeNotFoundError):
        resolve_locode(client, "ZZZZZ", {})


def test_request_scoped_cache_avoids_a_second_live_call_for_the_same_locode():
    client = _FakeMasterdataClient({"CNSHA": {"lon": 121.5, "lat": 31.2}})
    request_cache: dict = {}
    resolve_locode(client, "CNSHA", request_cache)
    resolve_locode(client, "CNSHA", request_cache)
    assert client.calls == ["CNSHA"]  # second lookup served from request_cache, not a second live call


def test_a_fresh_request_cache_never_carries_over_a_prior_requests_resolution():
    """D9's Step 5 correction: the caller must build a NEW request_cache per
    request -- reusing one across requests would silently defeat D9's
    staleness detection."""
    client = _FakeMasterdataClient({"CNSHA": {"lon": 121.5, "lat": 31.2}})
    resolve_locode(client, "CNSHA", {})
    resolve_locode(client, "CNSHA", {})  # a second, independent request_cache
    assert client.calls == ["CNSHA", "CNSHA"]
