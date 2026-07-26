"""Live smoke test against a REAL running geo-api (must already be up,
`docker compose ... --profile platform up -d` or `uv run geo-api`) plus a
real Keycloak for a client_credentials token. Skips (not fails) if either
isn't reachable -- same convention as
src/tms-mcp/tests/test_capacity_checkpoint.py.

A known lane leg (CNSHA -> DEHAM, ocean) must return a distance_km in the
same real-world-plausible ballpark the old committed
route-geometry/SHA-HAM-MUC.geojson had before that file was deleted (M10)
-- a regression check that the migrated routing algorithm still produces
the same real-world-plausible result, not just that it returns SOMETHING.
Confirmed manually during M10 development: ~20,600 km, matching real
Shanghai-Hamburg-via-Suez shipping distance."""

from __future__ import annotations

import os

import httpx
import pytest

KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://localhost:8081")
GEO_API_URL = os.environ.get("GEO_API_URL", "http://127.0.0.1:8400")


def _keycloak_up() -> bool:
    try:
        return httpx.get(f"{KEYCLOAK_URL}/realms/rfq", timeout=1.0).status_code == 200
    except Exception:
        return False


def _geo_api_up() -> bool:
    try:
        return httpx.get(f"{GEO_API_URL}/healthz", timeout=1.0).status_code == 200
    except Exception:
        return False


def _client_credentials_token(client_id: str, client_secret: str) -> str | None:
    if not client_secret:
        return None
    r = httpx.post(
        f"{KEYCLOAK_URL}/realms/rfq/protocol/openid-connect/token",
        data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
    )
    if r.status_code != 200:
        return None
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def token():
    if not (_keycloak_up() and _geo_api_up()):
        pytest.skip(f"Keycloak ({KEYCLOAK_URL}) or geo-api ({GEO_API_URL}) not running")
    from geo_api import settings
    try:
        secret = settings.introspection_client_secret()
    except Exception:
        pytest.skip("geo-api-svc-client-secret not available (Vault not seeded)")
    tok = _client_credentials_token(settings.KEYCLOAK_CLIENT_ID, secret)
    if not tok:
        pytest.skip("client_credentials grant failed for geo-api-svc")
    return tok


def test_shanghai_hamburg_ocean_leg_returns_a_plausible_distance(token):
    r = httpx.get(
        f"{GEO_API_URL}/v1/legs/geometry",
        params={"from": "CNSHA", "to": "DEHAM", "mode": "ocean"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=120.0,  # first hit runs a real A* pass -- see README's cache section
    )
    assert r.status_code == 200
    body = r.json()
    assert body["geometry"]["type"] in ("LineString", "MultiLineString")
    # Real-world Shanghai-Hamburg-via-Suez shipping distance is ~19,000-21,000 km.
    assert 15_000 < body["distance_km"] < 25_000
