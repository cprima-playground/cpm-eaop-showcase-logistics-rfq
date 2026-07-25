"""Offline test suite -- QMS_API_KEY set explicitly, stub masterdata/rate/fx/
tms clients (no network). Matches mock-rate/mock-tms/mock-fx's own
conftest.py pattern. Autouse here (unit/ only) -- integration/ and
business/ need the real live services these stubs would otherwise mask."""

import pytest

import mock_qms.api as api_module
import mock_qms.auth as auth_module

TEST_API_KEY = "test-qms-key"

# matches systems/masterdata/fixtures/parties.jsonl
_KNOWN_PARTIES = {"ACME": "customer", "COSCO": "carrier", "MAERSK": "carrier"}

# matches systems/masterdata/fixtures/currencies.jsonl (minor_unit values only)
_KNOWN_CURRENCIES = {"EUR": 2, "CNY": 2, "USD": 2, "GBP": 2, "JPY": 0}


class StubMasterdataClient:
    def get(self, domain: str, code: str):
        if domain == "parties" and code in _KNOWN_PARTIES:
            return {"party_id": code, "kind": _KNOWN_PARTIES[code]}
        if domain == "currencies" and code in _KNOWN_CURRENCIES:
            return {"code": code, "minor_unit": _KNOWN_CURRENCIES[code]}
        return None

    def list(self, domain: str):
        return []

    def exists(self, domain: str, code: str) -> bool:
        return self.get(domain, code) is not None


@pytest.fixture(autouse=True)
def _qms_api_key(monkeypatch):
    monkeypatch.setenv("QMS_API_KEY", TEST_API_KEY)
    auth_module._cached_key = None
    yield
    auth_module._cached_key = None


@pytest.fixture(autouse=True)
def _stub_masterdata(monkeypatch):
    monkeypatch.setattr(api_module, "_masterdata_client", lambda: StubMasterdataClient())
    yield


# matches systems/rate/fixtures/rates.yaml's real SHA-HAM-MUC entry
class StubRateClient:
    def get_rate(self, route_id: str):
        if route_id == "SHA-HAM-MUC":
            return {"route_id": route_id, "carrier_id": "COSCO", "currency": "CNY", "base_cost": 42000, "surcharges": 5100}
        if route_id == "SHA-RTM-MUC":
            return {"route_id": route_id, "carrier_id": "MAERSK", "currency": "EUR", "base_cost": 565000, "surcharges": 48000}
        return None


class StubFxClient:
    """Deterministic fixed rate per call -- test controls it via a class
    attribute so a test can simulate the rate moving between two price()
    calls (the FX-breakout scenario)."""

    rate = 0.13

    def convert(self, amount: str, from_currency: str, to_currency: str) -> dict:
        converted = round(float(amount) * self.rate, 2)
        return {
            "amount": amount, "from_currency": from_currency, "to_currency": to_currency,
            "rate": self.rate, "rate_ref": "FX-TEST", "converted_amount": str(converted), "minor_unit": 2,
        }


@pytest.fixture(autouse=True)
def _stub_rate_fx(monkeypatch):
    StubFxClient.rate = 0.13  # reset between tests
    monkeypatch.setattr(api_module, "_rate_client", lambda: StubRateClient())
    monkeypatch.setattr(api_module, "_fx_client", lambda: StubFxClient())
    yield


# matches systems/tms/fixtures/route-availability.yaml's baseline (all "available")
class StubTmsClient:
    _states: dict[str, dict] = {}

    def get_route_state(self, route_id: str):
        if route_id in self._states:
            return self._states[route_id]
        if route_id in ("SHA-HAM-MUC", "SHA-RTM-MUC"):
            return {"route_id": route_id, "status": "available"}
        return None


@pytest.fixture(autouse=True)
def _stub_tms(monkeypatch):
    StubTmsClient._states = {}  # reset between tests
    monkeypatch.setattr(api_module, "_tms_client", lambda: StubTmsClient())
    yield


TEST_SESSION_SECRET = "test-qms-session-secret"


@pytest.fixture(autouse=True)
def _qms_session_secret(monkeypatch):
    monkeypatch.setenv("QMS_SESSION_SECRET", TEST_SESSION_SECRET)
    import mock_qms.config as config_module
    config_module._cached_session_secret = None
    yield
    config_module._cached_session_secret = None
