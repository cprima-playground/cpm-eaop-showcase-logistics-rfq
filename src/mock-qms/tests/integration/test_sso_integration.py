"""Proves the QMS frontend's SSO/role-gating actually works end to end
against a REAL Keycloak (infra/keycloak/). Skips (not fails) if Keycloak
isn't running. Uses the ROPC/password grant (direct_access_grants_enabled
on qms-web is a deliberate test-only deviation, see
infra/keycloak/terraform/keycloak-qms.tf) to mint a token for each of the
4 real QMS users without driving a browser through the PKCE redirect dance
-- then verifies the token via rfq_common.verify.fetch_jwks/verify_with_jwks
+ resolve_principal(), exactly as mock_qms/sso.py's real /callback does,
and confirms the role-gate + the two custom claims (manager,
approval_limit_eur_cents)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from rfq_common.identity import resolve_principal
from rfq_common.secrets import SecretsClient
from rfq_common.verify import fetch_jwks, verify_with_jwks

import mock_qms.config as config

from conftest import service_up

KEYCLOAK_URL = "https://keycloak.eaop-logistics.localhost"  # via infra/caddy -- must match mock_qms.config's issuer
REALM_URL = f"{KEYCLOAK_URL}/realms/rfq"
CLIENT_ID = "qms-web"
RFQ_ROOT = Path(__file__).resolve().parents[4]
INVENTORY_PATH = RFQ_ROOT / "identity" / "credentials-inventory.yaml"
CA_BUNDLE = config.caddy_ca_bundle()
SSL_CONTEXT = config.caddy_ssl_context()


@pytest.fixture(scope="module")
def client_secret():
    if not service_up(f"{REALM_URL}/.well-known/openid-configuration", verify=SSL_CONTEXT):
        pytest.skip(f"keycloak not running on {KEYCLOAK_URL}")
    try:
        return SecretsClient("dev", inventory_path=INVENTORY_PATH).get("qms-web-client-secret")
    except Exception:
        pytest.skip("Vault not running or qms-web-client-secret not seeded")


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


def test_diane_resolves_to_reader_only(client_secret):
    principal = resolve_principal(_verify(_token_for("diane.delgado", client_secret)).claims)
    assert principal.kind == "human"
    assert principal.has_role("reader")
    assert not principal.has_role("commercial-manager")
    assert principal.manager is None
    assert principal.approval_limit_eur_cents is None


def test_mona_resolves_with_commercial_manager_role_and_approval_limit(client_secret):
    principal = resolve_principal(_verify(_token_for("mona.commercial", client_secret)).claims)
    assert principal.kind == "human"
    assert principal.has_role("commercial-manager")
    assert principal.groups == ["/rfq-commercial-emea"]
    assert principal.manager == "diane.delgado"
    assert principal.approval_limit_eur_cents == 1000000


def test_sam_resolves_with_pricing_manager_role(client_secret):
    principal = resolve_principal(_verify(_token_for("sam.pricing", client_secret)).claims)
    assert principal.has_role("pricing-manager")
    assert principal.groups == ["/rfq-pricing-emea"]
    # sam.pricing reports to the Pricing Manager, not the Regional Director
    # directly (capability-profile review correction, identity/actors.yaml's
    # own comment on this entry) -- was stale here since that correction.
    assert principal.manager == "mona.commercial"
    assert principal.approval_limit_eur_cents is None


def test_aiden_resolves_with_administrator_role(client_secret):
    principal = resolve_principal(_verify(_token_for("aiden.ashford", client_secret)).claims)
    assert principal.has_role("administrator")
    assert principal.groups == ["/rfq-qms-platform"]


def test_approvals_via_real_token_200_for_mona_403_for_others(client_secret, monkeypatch):
    from fastapi.testclient import TestClient

    import mock_qms.api as api_module

    class _StubMasterdata:
        def get(self, domain, code):
            return {"party_id": code, "kind": "customer"}

        def list(self, domain):
            return []

        def exists(self, domain, code):
            return True

    monkeypatch.setattr(api_module, "_masterdata_client", lambda: _StubMasterdata())
    app = api_module.build_app()

    for username, expected_status in [("mona.commercial", 200), ("diane.delgado", 403), ("aiden.ashford", 403)]:
        principal = resolve_principal(_verify(_token_for(username, client_secret)).claims)
        monkeypatch.setattr(api_module, "_current_principal", lambda request, p=principal: p)
        r = TestClient(app).get("/app/approvals")
        assert r.status_code == expected_status, f"{username}: expected {expected_status}, got {r.status_code}"
