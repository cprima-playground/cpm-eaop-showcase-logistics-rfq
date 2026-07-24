"""Keeps the offline test suite Vault- and masterdata-independent: FX_API_KEY is
set explicitly per test, and a stub MasterdataClient replaces the real one so
these tests never need live masterdata running (the separate skip-gated
test_masterdata_integration.py proves the REAL call)."""

import pytest

import mock_fx.api as api_module
import mock_fx.auth as auth_module

TEST_API_KEY = "test-fx-key"

# code -> minor_unit, matching the real masterdata fixtures (systems/masterdata/fixtures/currencies.jsonl)
_KNOWN_CURRENCIES = {"EUR": 2, "CNY": 2, "USD": 2, "GBP": 2, "JPY": 0, "SGD": 2, "CHF": 2}


class StubMasterdataClient:
    """Same interface as rfq_common.masterdata_client.MasterdataClient, backed
    by the same real currency list, no network."""

    def get(self, domain: str, code: str):
        if domain == "currencies" and code in _KNOWN_CURRENCIES:
            return {"code": code, "minor_unit": _KNOWN_CURRENCIES[code]}
        return None

    def list(self, domain: str):
        if domain == "currencies":
            return [{"code": c, "minor_unit": m} for c, m in _KNOWN_CURRENCIES.items()]
        return []

    def exists(self, domain: str, code: str) -> bool:
        return self.get(domain, code) is not None


@pytest.fixture(autouse=True)
def _fx_api_key(monkeypatch):
    monkeypatch.setenv("FX_API_KEY", TEST_API_KEY)
    auth_module._cached_key = None
    yield
    auth_module._cached_key = None


@pytest.fixture(autouse=True)
def _stub_masterdata(monkeypatch):
    """Offline tests never call the real masterdata service."""
    monkeypatch.setattr(api_module, "_masterdata_client", lambda: StubMasterdataClient())
    yield
