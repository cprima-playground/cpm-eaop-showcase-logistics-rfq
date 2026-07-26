"""M7 item 4: re-auth -- verify (not build) that MCP servers never cache
introspection results. Source-level guarantee (rfq_common.mcp_auth.verify.
IntrospectionTokenVerifier.verify(), read directly): every call makes a
fresh httpx.post to the introspection endpoint, no memoization anywhere
in the class -- true for all 4 M6 MCP servers, since every one of them
was fixed this session to build its verifier via the same
build_token_verifier(mode="introspection", ...) call.

Proven BEHAVIORALLY here, not just re-asserted from source, against
tms-mcp's real build_app() (in-process ASGI over TestClient, real
Keycloak + real cedar-agent -- same posture as test_capacity_checkpoint.
py, mechanically reused rather than duplicated) -- the concrete
acceptance criterion M7 states: "Revocation mid-session: next call fails
immediately, no stale permit." If introspection results were ever
cached, this test would fail: the second call would still succeed on a
cached prior "active": true result instead of re-checking with Keycloak
and observing the real revocation.

Deliberately does NOT drive this through the live compose deployment
(infra/compose.support.yaml + compose.showcase.yaml): that stack's
Keycloak issuer is hostname-dependent (KC_HOSTNAME/frontend-URL derived
from the request's own Host header), so a token minted from the host
(via Caddy or the :8081 admin carve-out) carries a different `iss` than
what tms-mcp's internal `http://keycloak:8080` introspection call
expects -- confirmed by direct reproduction this session, a real,
separate infra finding (Keycloak hostname consistency across the
Caddy-fronted vs. internal-DNS paths), not a caching bug, and not fixed
here. In-process build_app() + a single consistent KEYCLOAK_URL sidesteps
it entirely, same as every other checkpoint test in this repo already
does.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

RFQ_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RFQ_ROOT / "src" / "tms-mcp" / "tests"))
sys.path.insert(0, str(RFQ_ROOT / "src" / "tms-mcp"))

from test_capacity_checkpoint import (  # noqa: E402
    CEDAR_URL,
    KEYCLOAK_URL,
    ROUTE_ID,
    real_directory_entities_loaded,  # noqa: F401 -- reused as a fixture
)
from tms_mcp.api import build_app  # noqa: E402


def _keycloak_up() -> bool:
    try:
        return httpx.get(f"{KEYCLOAK_URL}/realms/rfq", timeout=1.0).status_code == 200
    except Exception:
        return False


def _cedar_up() -> bool:
    try:
        return httpx.get(f"{CEDAR_URL}/v1/policies", timeout=1.0).status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def preconditions():
    if not (_keycloak_up() and _cedar_up()):
        pytest.skip("Keycloak (:8081) or cedar-agent (:8280) not running")


@pytest.fixture(scope="module")
def app(preconditions, real_directory_entities_loaded):
    return build_app(root=RFQ_ROOT, cedar_url=CEDAR_URL)


@pytest.fixture(scope="module")
def client(app):
    return TestClient(app)


@pytest.fixture()
def client_secret():
    secret = os.environ.get("LANE_EVAL_AGENT_SECRET", "")
    if not secret:
        pytest.skip("LANE_EVAL_AGENT_SECRET not set -- see README")
    return secret


def test_revoked_token_is_denied_on_the_very_next_call_no_stale_permit(client, client_secret):
    token_resp = httpx.post(
        f"{KEYCLOAK_URL}/realms/rfq/protocol/openid-connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "lane-evaluation-agent-svc",
            "client_secret": client_secret,
        },
        timeout=5.0,
    )
    if token_resp.status_code != 200:
        pytest.skip(f"Keycloak rejected LANE_EVAL_AGENT_SECRET: {token_resp.status_code} {token_resp.text}")
    token = token_resp.json()["access_token"]

    first = client.post(
        "/tools/check_lane_capacity",
        json={"route_id": ROUTE_ID},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 200, f"expected the fresh token to be accepted: {first.status_code} {first.text}"

    revoke_resp = httpx.post(
        f"{KEYCLOAK_URL}/realms/rfq/protocol/openid-connect/revoke",
        data={
            "token": token,
            "client_id": "lane-evaluation-agent-svc",
            "client_secret": client_secret,
        },
        timeout=5.0,
    )
    assert revoke_resp.status_code == 200, revoke_resp.text

    second = client.post(
        "/tools/check_lane_capacity",
        json={"route_id": ROUTE_ID},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second.status_code == 401, (
        f"revoked token still accepted -- introspection result was cached, "
        f"stale permit: {second.status_code} {second.text}"
    )
