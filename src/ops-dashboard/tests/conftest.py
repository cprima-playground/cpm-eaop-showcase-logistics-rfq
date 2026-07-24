"""Offline test suite -- stub TMS/Rate/Masterdata clients (no network), session
secret set explicitly, principal pre-seeded into the session to bypass a real
Keycloak login for view/role-gate tests. The separate skip-gated
test_sso_integration.py proves the real login round-trip."""

import pytest

import ops_dashboard.api as api_module
import ops_dashboard.config as config_module

TEST_SESSION_SECRET = "test-session-secret"


class StubTmsClient:
    base_url = "http://stub-tms"

    def __init__(self):
        self._routes = [
            {
                "id": "SHA-HAM-MUC", "lane": "CNSHA-DEMUC", "contracted": True,
                "legs": [{"from": "CNSHA", "to": "DEHAM", "mode": "ocean", "duration_days": 27}],
            },
            {
                "id": "SHA-RTM-MUC", "lane": "CNSHA-DEMUC", "contracted": False,
                "legs": [
                    {"from": "CNSHA", "to": "NLRTM", "mode": "ocean", "duration_days": 26},
                    {"from": "NLRTM", "to": "DEDUI", "mode": "rail", "duration_days": 1},
                ],
            },
        ]
        self._availability = {
            "SHA-HAM-MUC": {"route_id": "SHA-HAM-MUC", "status": "available", "reason": None},
            "SHA-RTM-MUC": {"route_id": "SHA-RTM-MUC", "status": "limited", "reason": "capacity"},
        }

    def list_routes(self):
        return list(self._routes)

    def get_route(self, route_id):
        return next((r for r in self._routes if r["id"] == route_id), None)

    def get_availability(self, route_id):
        return self._availability.get(route_id)


class StubRateClient:
    base_url = "http://stub-rate"

    def get_rate(self, route_id):
        if route_id == "SHA-HAM-MUC":
            return {"route_id": route_id, "carrier_id": "COSCO", "currency": "CNY", "base_cost": 42000, "surcharges": 5100}
        return None

    def list_rates(self):
        return []


_LOCATIONS = {
    "CNSHA": {"locode": "CNSHA", "name": "Shanghai", "lat": 31.23, "lon": 121.47},
    "DEHAM": {"locode": "DEHAM", "name": "Hamburg", "lat": 53.55, "lon": 9.99},
    "NLRTM": {"locode": "NLRTM", "name": "Rotterdam", "lat": 51.95, "lon": 4.14},
    "DEDUI": {"locode": "DEDUI", "name": "Duisburg", "lat": 51.43, "lon": 6.77},
}


class StubMasterdataClient:
    base_url = "http://stub-masterdata"

    def get(self, domain, code):
        if domain == "locations":
            return _LOCATIONS.get(code)
        return {"locode": code}

    def list(self, domain):
        if domain == "currencies":
            return [{"code": "CNY", "name": "Chinese Yuan"}, {"code": "EUR", "name": "Euro"}]
        return []

    def exists(self, domain, code):
        return True


class StubFxClient:
    base_url = "http://stub-fx"

    def get_rate(self, base, quote):
        if (base, quote) == ("CNY", "EUR"):
            return {"pair": "CNY-EUR", "rate": 0.1194, "source": "test-fixture",
                     "observed_at": "2026-07-24T00:00:00Z", "valid_until": None, "rate_ref": "fx-test-1"}
        return None

    def get_rate_history(self, base, quote, days=30):
        if (base, quote) != ("CNY", "EUR"):
            return []
        return [
            {"pair": "CNY/EUR", "rate": 0.1210, "observed_at": "2026-07-22T08:00:00Z", "rate_ref": "fx-test-0"},
            {"pair": "CNY/EUR", "rate": 0.1226, "observed_at": "2026-07-23T08:00:00Z", "rate_ref": "fx-test-1226"},
            {"pair": "CNY/EUR", "rate": 0.1194, "observed_at": "2026-07-24T08:00:00Z", "rate_ref": "fx-test-1194"},
        ]


@pytest.fixture(autouse=True)
def _session_secret(monkeypatch):
    monkeypatch.setenv("OPS_DASHBOARD_SESSION_SECRET", TEST_SESSION_SECRET)
    config_module._cached_session_secret = None
    yield
    config_module._cached_session_secret = None


@pytest.fixture
def stub_clients():
    return StubTmsClient(), StubRateClient(), StubMasterdataClient(), StubFxClient()


@pytest.fixture
def app(stub_clients):
    tms, rate, masterdata, fx = stub_clients
    return api_module.build_app(tms_client=tms, rate_client=rate, masterdata_client=masterdata, fx_client=fx)
