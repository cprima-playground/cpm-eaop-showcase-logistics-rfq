from fastapi.testclient import TestClient

from conftest import TEST_API_KEY as API_KEY
from mock_masterdata.api import build_app
from mock_masterdata.store import DOMAINS


def client():
    return TestClient(build_app())


def test_healthz():
    assert client().get("/healthz").status_code == 200


def test_swagger_ui_reachable():
    r = client().get("/swagger")
    assert r.status_code == 200
    assert "swagger" in r.text.lower()


def test_openapi_title():
    r = client().get("/openapi.json")
    assert r.json()["info"]["title"] == "Masterdata Source"


def test_list_requires_api_key():
    r = client().get("/currencies")
    assert r.status_code == 401


def test_list_currencies():
    r = client().get("/currencies", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    codes = {c["code"] for c in r.json()}
    assert {"EUR", "CNY", "USD"}.issubset(codes)


def test_get_one_location():
    r = client().get("/locations/CNSHA", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert r.json()["name"] == "Shanghai"


def test_get_unknown_code_404():
    r = client().get("/currencies/XXX", headers={"X-API-Key": API_KEY})
    assert r.status_code == 404


def test_every_domain_has_a_working_route():
    c = client()
    for domain in DOMAINS:
        r = c.get(f"/{domain}", headers={"X-API-Key": API_KEY})
        assert r.status_code == 200, f"{domain} list route failed"
        assert len(r.json()) > 0, f"{domain} is empty"


def test_admin_reset():
    r = client().post("/admin/reset", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert set(r.json()["domains"]) == set(DOMAINS)
