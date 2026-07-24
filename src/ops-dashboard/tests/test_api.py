import httpx
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


def test_route_detail_includes_mini_map(app, monkeypatch):
    monkeypatch.setattr(api_module, "_current_principal", lambda request: VIEWER)
    r = TestClient(app).get("/routes/SHA-HAM-MUC")
    assert r.status_code == 200
    assert "route-detail-map" in r.text
    assert "rmDrawRoutes" in r.text


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


def test_map_splits_antimeridian_crossing_routes(app, monkeypatch):
    """CNSHA (lon ~121E) -> USLAX (lon ~-118W) must NOT draw the long way
    through Europe/Africa -- regression for the bug the user's screenshot
    caught live. Split into two segments (flight-path convention), not a
    single unwrapped line past +-180 -- a vector basemap doesn't repeat past
    that range the way a raster tile layer would."""
    monkeypatch.setattr(api_module, "_current_principal", lambda request: VIEWER)
    client = TestClient(app)
    r = client.get("/map")
    assert r.status_code == 200
    assert "/static/js/route-map.js" in r.text
    js = client.get("/static/js/route-map.js")
    assert js.status_code == 200
    assert "splitAtAntimeridian" in js.text


def test_map_shows_intermediate_waypoints_not_just_endpoints(app, monkeypatch):
    """SHA-RTM-MUC (CNSHA -> Rotterdam -> Duisburg) must show Rotterdam as a
    real bend, not draw identically to a direct route (KNOWN-ISSUES.md #12)."""
    monkeypatch.setattr(api_module, "_current_principal", lambda request: VIEWER)
    r = TestClient(app).get("/map")
    assert r.status_code == 200
    assert "51.95" in r.text  # Rotterdam lat -- the intermediate waypoint
    assert "51.43" in r.text  # Duisburg lat -- the final destination


def test_map_requires_role(app):
    r = TestClient(app).get("/map", follow_redirects=False)
    assert r.status_code in (302, 303, 307)


def test_map_static_geojson_served(app):
    r = TestClient(app).get("/static/vendor/natural-earth/ne_110m_admin_0_countries.geojson")
    assert r.status_code == 200
    assert r.json()["type"] == "FeatureCollection"


def _fake_healthz_response(status_code=200):
    return httpx.Response(status_code, request=httpx.Request("GET", "http://stub/healthz"))


def test_check_service_pass_when_healthz_and_auth_both_ok(monkeypatch):
    monkeypatch.setattr(api_module.httpx, "get", lambda *a, **k: _fake_healthz_response(200))
    result = api_module._check_service("tms", "http://stub", lambda: {"ok": True})
    assert result["status"] == "pass"
    assert result["reachable"] is True
    assert result["authenticated"] is True


def test_check_service_fail_when_unreachable(monkeypatch):
    def _raise(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(api_module.httpx, "get", _raise)
    result = api_module._check_service("tms", "http://stub", lambda: None)
    assert result["status"] == "fail"
    assert result["reachable"] is False
    assert "unreachable" in result["detail"]


def test_check_service_warn_on_stale_credential_401(monkeypatch):
    """The exact failure mode caught live: a running consumer's cached API
    key stops matching after Vault reseeds it -- service is UP, but OUR call
    401s. Must be distinguishable from the service being down entirely."""
    monkeypatch.setattr(api_module.httpx, "get", lambda *a, **k: _fake_healthz_response(200))

    def _probe():
        raise httpx.HTTPStatusError(
            "401", request=httpx.Request("GET", "http://stub/x"),
            response=httpx.Response(401, request=httpx.Request("GET", "http://stub/x")),
        )

    result = api_module._check_service("fx", "http://stub", _probe)
    assert result["status"] == "warn"
    assert result["reachable"] is True
    assert result["authenticated"] is False
    assert "401" in result["detail"]
    assert "KNOWN-ISSUES.md" in result["detail"]


def test_status_page_shows_overall_pass_when_all_services_ok(app, monkeypatch):
    monkeypatch.setattr(api_module, "_current_principal", lambda request: VIEWER)
    monkeypatch.setattr(api_module.httpx, "get", lambda *a, **k: _fake_healthz_response(200))
    r = TestClient(app).get("/status")
    assert r.status_code == 200
    assert "Overall: pass" in r.text
    assert "tms" in r.text and "masterdata" in r.text and "rate" in r.text and "fx" in r.text


def test_status_requires_role(app):
    r = TestClient(app).get("/status", follow_redirects=False)
    assert r.status_code in (302, 303, 307)


def test_correlation_id_header_present(app, monkeypatch):
    monkeypatch.setattr(api_module, "_current_principal", lambda request: VIEWER)
    r = TestClient(app).get("/")
    assert "X-Correlation-Id" in r.headers


def test_swagger_ui_reachable(app):
    r = TestClient(app).get("/docs")
    assert r.status_code == 200
