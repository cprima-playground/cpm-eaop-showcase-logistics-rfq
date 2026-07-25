from fastapi.testclient import TestClient

from conftest import TEST_API_KEY as API_KEY
from mock_tms.api import build_app


def client():
    return TestClient(build_app())


def test_healthz():
    assert client().get("/healthz").status_code == 200


def test_swagger_ui_reachable():
    r = client().get("/swagger")
    assert r.status_code == 200
    assert "swagger" in r.text.lower()


def test_routes_requires_api_key():
    assert client().get("/routes").status_code == 401


def test_list_routes():
    r = client().get("/routes", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert len(r.json()) == 17


def test_get_route():
    r = client().get("/routes/SHA-HAM-MUC", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert "contracted" in r.json()["roles"]
    assert r.json()["legs"][0]["origin_id"] == "CNSHA"


def test_get_unknown_route_404():
    r = client().get("/routes/NOPE", headers={"X-API-Key": API_KEY})
    assert r.status_code == 404


def test_availability():
    r = client().get("/routes/SHA-HAM-MUC/availability", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert r.json()["status"] == "available"


def test_transit_time():
    r = client().get("/routes/SHA-HAM-MUC/transit-time", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert r.json()["transit_days"] == 29


def test_capacity():
    r = client().get("/routes/SHA-HAM-MUC/capacity", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert r.json()["capacity_status"] == "available"


def test_feasible_lanes():
    r = client().get("/feasible-lanes", params={"lane": "CNSHA-DEMUC"}, headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert len(r.json()) == 8  # all routes on the lane; see test_store.py's note


def test_get_new_geography_route():
    r = client().get("/routes/MEA-SUEZ", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert r.json()["lane_id"] == "AEJEA-DEHAM"
    assert r.json()["legs"][0]["origin_id"] == "AEJEA"


def test_list_edges_returns_deterministic_29_entry_pool():
    r = client().get("/edges", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    edges = r.json()
    assert len(edges) == 29
    assert [e["id"] for e in edges] == sorted(e["id"] for e in edges)


def test_edges_requires_api_key():
    assert client().get("/edges").status_code == 401


def test_route_applicability_tag_present():
    r = client().get("/routes/SHA-RTM-MUC", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert r.json()["applicability"]["applicable_disruption_tags"] == ["hamburg_ocean_gateway_unavailable"]


def test_feasible_lanes_new_geography():
    r = client().get("/feasible-lanes", params={"lane": "CNSHA-USLAX"}, headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert len(r.json()) == 2

    r = client().get("/feasible-lanes", params={"lane": "NLRTM-ITMIL"}, headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_admin_reset():
    r = client().post("/admin/reset", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert r.json()["status"] == "reset"


def test_patch_availability_updates_live_state():
    c = client()
    r = c.patch(
        "/routes/SHA-HAM-MUC/availability",
        json={"status": "unavailable", "reason": "port congestion"},
        headers={"X-API-Key": API_KEY},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "unavailable"
    assert r.json()["reason"] == "port congestion"

    r = c.get("/routes/SHA-HAM-MUC/availability", headers={"X-API-Key": API_KEY})
    assert r.json()["status"] == "unavailable"


def test_patch_availability_unknown_route_404():
    r = client().patch(
        "/routes/NOPE/availability",
        json={"status": "unavailable"},
        headers={"X-API-Key": API_KEY},
    )
    assert r.status_code == 404


def test_patch_availability_requires_api_key():
    r = client().patch("/routes/SHA-HAM-MUC/availability", json={"status": "unavailable"})
    assert r.status_code == 401


def test_admin_reset_discards_patch_mutation():
    c = client()
    c.patch(
        "/routes/SHA-HAM-MUC/availability",
        json={"status": "unavailable", "reason": "port congestion"},
        headers={"X-API-Key": API_KEY},
    )
    r = c.post("/admin/reset", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200

    r = c.get("/routes/SHA-HAM-MUC/availability", headers={"X-API-Key": API_KEY})
    assert r.json()["status"] == "available"
