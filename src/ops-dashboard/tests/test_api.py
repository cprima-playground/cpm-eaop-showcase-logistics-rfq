from fastapi.testclient import TestClient

import ops_dashboard.api as api_module
from rfq_common.identity import Principal

VIEWER = Principal(kind="human", id="alice", roles=["ops-viewer"])
NO_ROLE = Principal(kind="human", id="bob", roles=[])


def test_healthz(app):
    assert TestClient(app).get("/healthz").status_code == 200


def test_dashboard_redirects_anonymous_to_login(app):
    r = TestClient(app).get("/", follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    assert r.headers["location"] == "/login"


def test_dashboard_403_without_role(app, monkeypatch):
    monkeypatch.setattr(api_module, "_current_principal", lambda request: NO_ROLE)
    r = TestClient(app).get("/")
    assert r.status_code == 403


def test_dashboard_200_with_role_shows_routes(app, monkeypatch):
    monkeypatch.setattr(api_module, "_current_principal", lambda request: VIEWER)
    r = TestClient(app).get("/")
    assert r.status_code == 200
    assert "SHA-HAM-MUC" in r.text
    assert "SHA-RTM-MUC" in r.text


def test_route_detail_200_with_rate(app, monkeypatch):
    monkeypatch.setattr(api_module, "_current_principal", lambda request: VIEWER)
    r = TestClient(app).get("/routes/SHA-HAM-MUC")
    assert r.status_code == 200
    assert "COSCO" in r.text
    assert "42000" in r.text


def test_route_detail_no_rate_on_file(app, monkeypatch):
    monkeypatch.setattr(api_module, "_current_principal", lambda request: VIEWER)
    r = TestClient(app).get("/routes/SHA-RTM-MUC")
    assert r.status_code == 200
    assert "No rate on file" in r.text


def test_route_detail_unknown_route_404(app, monkeypatch):
    monkeypatch.setattr(api_module, "_current_principal", lambda request: VIEWER)
    r = TestClient(app).get("/routes/NOPE")
    assert r.status_code == 404


def test_fx_lookup_default_pair_found(app, monkeypatch):
    monkeypatch.setattr(api_module, "_current_principal", lambda request: VIEWER)
    r = TestClient(app).get("/fx")
    assert r.status_code == 200
    assert "CNY-EUR" in r.text
    assert "0.1194" in r.text


def test_fx_lookup_unknown_pair(app, monkeypatch):
    monkeypatch.setattr(api_module, "_current_principal", lambda request: VIEWER)
    r = TestClient(app).get("/fx", params={"base": "USD", "quote": "JPY"})
    assert r.status_code == 200
    assert "No rate on file" in r.text


def test_fx_requires_role(app):
    r = TestClient(app).get("/fx", follow_redirects=False)
    assert r.status_code in (302, 303, 307)


def test_masterdata_domain_list(app, monkeypatch):
    monkeypatch.setattr(api_module, "_current_principal", lambda request: VIEWER)
    r = TestClient(app).get("/masterdata")
    assert r.status_code == 200
    assert "currencies" in r.text
    assert "locations" in r.text


def test_masterdata_domain_detail(app, monkeypatch):
    monkeypatch.setattr(api_module, "_current_principal", lambda request: VIEWER)
    r = TestClient(app).get("/masterdata/currencies")
    assert r.status_code == 200
    assert "CNY" in r.text
    assert "EUR" in r.text


def test_masterdata_unknown_domain_404(app, monkeypatch):
    monkeypatch.setattr(api_module, "_current_principal", lambda request: VIEWER)
    r = TestClient(app).get("/masterdata/not-a-domain")
    assert r.status_code == 404


def test_map_shows_both_routes_with_coordinates(app, monkeypatch):
    monkeypatch.setattr(api_module, "_current_principal", lambda request: VIEWER)
    r = TestClient(app).get("/map")
    assert r.status_code == 200
    assert "SHA-HAM-MUC" in r.text
    assert "31.23" in r.text  # Shanghai lat, from the stub location
    assert "leaflet" in r.text.lower()


def test_map_requires_role(app):
    r = TestClient(app).get("/map", follow_redirects=False)
    assert r.status_code in (302, 303, 307)


def test_map_static_geojson_served(app):
    r = TestClient(app).get("/static/vendor/natural-earth/ne_110m_admin_0_countries.geojson")
    assert r.status_code == 200
    assert r.json()["type"] == "FeatureCollection"


def test_correlation_id_header_present(app, monkeypatch):
    monkeypatch.setattr(api_module, "_current_principal", lambda request: VIEWER)
    r = TestClient(app).get("/")
    assert "X-Correlation-Id" in r.headers


def test_swagger_ui_reachable(app):
    r = TestClient(app).get("/docs")
    assert r.status_code == 200
