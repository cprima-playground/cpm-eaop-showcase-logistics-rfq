"""Offline-safe: exercises MasterdataClient against a live masterdata instance
if one happens to be up (skips gracefully otherwise -- this module's own
correctness doesn't require live infra; FX's integration test is the one that
must have masterdata running)."""

import httpx
import pytest

from rfq_common.masterdata_client import MasterdataClient, MasterdataUnavailableError


def test_unreachable_host_raises_masterdata_unavailable():
    client = MasterdataClient(base_url="http://localhost:1", timeout=0.5)
    with pytest.raises(MasterdataUnavailableError):
        client.get("currencies", "EUR")


def test_exists_false_on_404(monkeypatch):
    class FakeResponse:
        status_code = 404

    def fake_get(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(httpx, "get", fake_get)
    client = MasterdataClient(base_url="http://fake")
    assert client.exists("currencies", "ZZZ") is False


def test_get_returns_json_on_200(monkeypatch):
    class FakeResponse:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {"code": "EUR", "name": "Euro"}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResponse())
    client = MasterdataClient(base_url="http://fake")
    assert client.get("currencies", "EUR") == {"code": "EUR", "name": "Euro"}
