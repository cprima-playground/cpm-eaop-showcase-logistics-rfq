"""build_app() wiring tests, all fakes injected -- no live Keycloak,
masterdata, or Vault required (same discipline as mission-control-api's
own test suite: nothing in tests/ needs Docker or a live stack to pass)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from geo_api.api import build_app
from geo_api.cache import LegGeometryCache
from geo_api.routing import MaritimeGraph


class _FakeMasterdataClient:
    def __init__(self, rows: dict[str, dict]):
        self._rows = rows

    def get(self, domain: str, code: str):
        assert domain == "locations"
        return self._rows.get(code)


FAKE_ROWS = {
    "AAAAA": {"lon": 10.0, "lat": 50.0},
    "BBBBB": {"lon": 11.0, "lat": 51.0},
}


def _test_app(tmp_path, **overrides):
    kwargs = dict(
        # Empty, not None -- None would trigger build_app()'s own
        # routing.load_graph() default (real YAML + landmask.register_clear_zone
        # side effects). Every test here uses mode="air", which never touches
        # the graph at all, so an empty one is a correct and cheap stand-in.
        graph=MaritimeGraph(nodes={}, adjacency={}, edge_kind={}),
        cache=LegGeometryCache(tmp_path / "cache.sqlite3"),
        masterdata_client=_FakeMasterdataClient(FAKE_ROWS),
        introspection_client_secret="test-secret",
        public_url="https://geo.eaop-logistics.localhost",
        instance_id="test-instance",
        routing_version_value="test-routing-version",
    )
    kwargs.update(overrides)
    return build_app(**kwargs)


def test_descriptor_reports_platform_kind_and_the_capability(tmp_path):
    client = TestClient(_test_app(tmp_path))
    r = client.get("/descriptor")
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "platform"
    assert body["canonical_id"] == "workload.geo-api"
    assert body["capabilities"]["skills"] == ["route.geometry.compute"]


def test_legs_geometry_without_a_token_is_401(tmp_path):
    client = TestClient(_test_app(tmp_path))
    r = client.get("/v1/legs/geometry", params={"from": "AAAAA", "to": "BBBBB", "mode": "air"})
    assert r.status_code == 401


def test_legs_geometry_with_a_bogus_token_is_401(tmp_path):
    client = TestClient(_test_app(tmp_path))
    r = client.get(
        "/v1/legs/geometry",
        params={"from": "AAAAA", "to": "BBBBB", "mode": "air"},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    # Introspection endpoint is unreachable in this test environment --
    # IntrospectionTokenVerifier.verify() converts that into AuthenticationError
    # too (verify.py), so this asserts the SAME fail-closed 401, not a 500.
    assert r.status_code == 401


def test_provenance_is_unauthenticated_like_descriptor_and_healthz(tmp_path):
    client = TestClient(_test_app(tmp_path))
    r = client.get("/v1/provenance")
    assert r.status_code == 200
    body = r.json()
    assert body["routing_version"] == "test-routing-version"
    assert "routing_algorithm_version" in body
    assert "maritime_graph_fingerprint" in body
    assert "keepout_zones_fingerprint" in body
