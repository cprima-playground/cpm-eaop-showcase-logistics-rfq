"""M8, built directly on M5.5's shared rfq_common.settings contract.
Mission Control's own introspection-auth client secret (OIDC_CLIENT_SECRET)
is the only credential this service holds -- it verifies inbound bearer
tokens (D6: authN yes, Cedar authZ deferred), it never calls cedar-agent's
/v1/is_authorized (see test_no_authorization_decisions.py, M8.4), and it
never reads another workload's Vault secret (D3: identity-drift is
declared-vs-Terraform-state only, no live-grant checks against other
identities' credentials)."""

from __future__ import annotations

from pathlib import Path

from rfq_common.settings import PrincipalCredentialSettings, ResourceServerSettings

RFQ_ROOT = Path(__file__).resolve().parents[3]
INVENTORY_PATH = RFQ_ROOT / "identity" / "credentials-inventory.yaml"

KEYCLOAK_CLIENT_ID = "mission-control-api-svc"  # identity/projections/keycloak.yaml: workload.mission-control
EXPECTED_CANONICAL_ID = "workload.mission-control"


def oidc_issuer_url() -> str:
    return ResourceServerSettings.from_env().oidc_issuer_url


def introspection_endpoint() -> str:
    return ResourceServerSettings.from_env().introspection_url


def introspection_client_secret() -> str:
    return PrincipalCredentialSettings.from_env(
        client_id=KEYCLOAK_CLIENT_ID,
        expected_canonical_id=EXPECTED_CANONICAL_ID,
        vault_secret_name="mission-control-api-svc-client-secret",
        inventory_path=INVENTORY_PATH,
    ).client_secret.get_secret_value()
