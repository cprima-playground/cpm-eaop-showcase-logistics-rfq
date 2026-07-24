from fastapi.testclient import TestClient

from conftest import TEST_API_KEY as API_KEY
from mock_rate.api import build_app


def client():
    return TestClient(build_app())


def test_healthz():
    assert client().get("/healthz").status_code == 200


def test_swagger_ui_reachable():
    r = client().get("/docs")
    assert r.status_code == 200
    assert "swagger" in r.text.lower()


def test_rates_requires_api_key():
    assert client().get("/rates").status_code == 401


def test_list_rates():
    r = client().get("/rates", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert len(r.json()) == 16


def test_get_rate():
    r = client().get("/rates/SHA-HAM-MUC", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    body = r.json()
    assert body["carrier_id"] == "COSCO"
    assert body["base_cost"] == 42000


def test_get_unknown_route_404():
    r = client().get("/rates/NOPE", headers={"X-API-Key": API_KEY})
    assert r.status_code == 404


def test_get_surcharges():
    r = client().get("/rates/SHA-HAM-MUC/surcharges", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert r.json()["surcharges"] == 5100


def test_get_rate_new_geography():
    r = client().get("/rates/MEA-SUEZ", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    body = r.json()
    assert body["carrier_id"] == "MSC"
    assert body["currency"] == "EUR"


def test_admin_reset():
    r = client().post("/admin/reset", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert r.json()["status"] == "reset"
