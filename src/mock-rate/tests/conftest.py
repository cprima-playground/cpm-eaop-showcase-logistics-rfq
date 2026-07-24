"""Offline test suite -- RATE_API_KEY set explicitly, stub masterdata client
(real carrier/currency data, no network). Separate skip-gated
test_masterdata_integration.py proves the real call."""

import pytest

import mock_rate.api as api_module
import mock_rate.auth as auth_module

TEST_API_KEY = "test-rate-key"

# matches systems/masterdata/fixtures/parties.jsonl + currencies.jsonl
_KNOWN_PARTIES = {
    "ACME": "customer", "COSCO": "carrier", "MAERSK": "carrier", "MSC": "carrier",
    "LUFTHANSA-CARGO": "carrier", "HAPAG-LLOYD": "carrier",
}
_KNOWN_CURRENCIES = {"EUR", "CNY", "USD", "GBP", "JPY", "SGD", "CHF"}


class StubMasterdataClient:
    def get(self, domain: str, code: str):
        if domain == "parties" and code in _KNOWN_PARTIES:
            return {"party_id": code, "kind": _KNOWN_PARTIES[code]}
        if domain == "currencies" and code in _KNOWN_CURRENCIES:
            return {"code": code}
        return None

    def list(self, domain: str):
        return []

    def exists(self, domain: str, code: str) -> bool:
        return self.get(domain, code) is not None


@pytest.fixture(autouse=True)
def _rate_api_key(monkeypatch):
    monkeypatch.setenv("RATE_API_KEY", TEST_API_KEY)
    auth_module._cached_key = None
    yield
    auth_module._cached_key = None


@pytest.fixture(autouse=True)
def _stub_masterdata(monkeypatch):
    monkeypatch.setattr(api_module, "_masterdata_client", lambda: StubMasterdataClient())
    yield
