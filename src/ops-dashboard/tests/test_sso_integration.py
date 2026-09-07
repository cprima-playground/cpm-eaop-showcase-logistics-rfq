"""Proves the ops-dashboard's SSO/role-gating actually works end to end
against a REAL Keycloak (infra/keycloak/). Skips (not fails) if Keycloak
isn't running. Uses the ROPC/password grant (direct_access_grants_enabled on
ops-dashboard-web is a deliberate test-only deviation, see
infra/keycloak/terraform/keycloak-sso.tf) to mint a token for alice/bob
without driving a browser through the PKCE redirect dance -- then verifies
the token via rfq_common.verify.fetch_jwks/verify_with_jwks + resolve_principal(),
exactly as ops_dashboard/sso.py's real /callback does, and confirms the role-gate."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from rfq_common.identity import resolve_principal
from rfq_common.secrets import SecretsClient
from rfq_common.verify import fetch_jwks, verify_with_jwks

import ops_dashboard.config as config

KEYCLOAK_URL = "https://keycloak.eaop-logistics.localhost"  # via infra/caddy -- must match ops_dashboard.config's issuer
REALM_URL = f"{KEYCLOAK_URL}/realms/rfq"
CLIENT_ID = "ops-dashboard-web"
RFQ_ROOT = Path(__file__).resolve().parents[3]
INVENTORY_PATH = RFQ_ROOT / "identity" / "credentials-inventory.yaml"
CA_BUNDLE = config.caddy_ca_bundle()
SSL_CONTEXT = config.caddy_ssl_context()


def _keycloak_up() -> bool:
    try:
        r = httpx.get(f"{REALM_URL}/.well-known/openid-configuration", timeout=1.0, verify=SSL_CONTEXT)
        return r.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def client_secret():
    if not _keycloak_up():
        pytest.skip(f"keycloak not running on {KEYCLOAK_URL}")
    try:
        return SecretsClient("dev", inventory_path=INVENTORY_PATH).get("ops-dashboard-web-client-secret")
    except Exception:
        pytest.skip("Vault not running or ops-dashboard-web-client-secret not seeded")


def _token_for(username: str, client_secret: str) -> str:
    r = httpx.post(
        f"{REALM_URL}/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": CLIENT_ID,
            "client_secret": client_secret,
            "username": username,
            "password": "rfq-dev-user",
            "scope": "openid",
        },
        timeout=10,
        verify=SSL_CONTEXT,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _verify(token: str):
    jwks = fetch_jwks(f"{REALM_URL}/protocol/openid-connect/certs", verify=CA_BUNDLE)
    return verify_with_jwks(token, jwks, issuer=REALM_URL, audience=CLIENT_ID)


def test_alice_resolves_to_human_with_ops_viewer_role(client_secret):
    token = _token_for("alice", client_secret)
    verified = _verify(token)
    principal = resolve_principal(verified.claims)
    assert principal.kind == "human"
    assert principal.has_role("ops-viewer")
    assert principal.groups == ["/Ops"]
    assert principal.tid == "rfq-dev-tenant"
    assert principal.oid is not None


def test_bob_resolves_to_human_without_ops_viewer_role(client_secret):
    token = _token_for("bob", client_secret)
    verified = _verify(token)
    principal = resolve_principal(verified.claims)
    assert principal.kind == "human"
    assert not principal.has_role("ops-viewer")


def test_dashboard_via_real_token_200_for_alice_403_for_bob(client_secret, monkeypatch):
    from fastapi.testclient import TestClient

    import ops_dashboard.api as api_module

    class _StubTms:
        def list_routes(self):
            return []

        def get_route(self, route_id):
            return None

        def get_availability(self, route_id):
            return None

    class _StubRate:
        def get_rate(self, route_id):
            return None

        def list_rates(self):
            return []

    class _StubMasterdata:
        def get(self, domain, code):
            return {"locode": code}

        def list(self, domain):
            return []

        def exists(self, domain, code):
            return True

    app = api_module.build_app(tms_client=_StubTms(), rate_client=_StubRate(), masterdata_client=_StubMasterdata())

    for username, expected_status in [("alice", 200), ("bob", 403)]:
        token = _token_for(username, client_secret)
        verified = _verify(token)
        principal = resolve_principal(verified.claims)
        monkeypatch.setattr(api_module, "_current_principal", lambda request, p=principal: p)
        r = TestClient(app).get("/")
        assert r.status_code == expected_status, f"{username}: expected {expected_status}, got {r.status_code}"
