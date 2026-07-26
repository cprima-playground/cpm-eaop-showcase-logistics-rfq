"""M6, built directly on M5.5's shared rfq_common.settings contract --
no legacy env-var aliases needed (this is a NEW service, not a
migration). Two distinct secrets, same distinction tms-mcp draws
(rfq_common.mcp_auth.verify's module docstring): rate-mcp's OWN
introspection-auth client secret (OIDC_CLIENT_SECRET) vs. the
rate-api-key it presents *downstream* to mock-rate (transport auth,
decision #8's accepted shared-key posture for this hop, same posture as
tms-mcp/tms-api-key)."""

from __future__ import annotations

import os
from pathlib import Path

from rfq_common.secrets import SecretsClient
from rfq_common.service_resolver import EnvironmentServiceResolver
from rfq_common.settings import CedarSettings, CredentialUnavailableError, PrincipalCredentialSettings, ResourceServerSettings

RFQ_ROOT = Path(__file__).resolve().parents[3]
INVENTORY_PATH = RFQ_ROOT / "identity" / "credentials-inventory.yaml"

KEYCLOAK_CLIENT_ID = "rate-mcp-svc"  # identity/projections/keycloak.yaml: workload.rate-mcp
EXPECTED_CANONICAL_ID = "workload.rate-mcp"


def keycloak_url() -> str:
    return ResourceServerSettings.from_env().keycloak_base_url


def introspection_endpoint() -> str:
    return ResourceServerSettings.from_env().introspection_url


def introspection_client_secret() -> str:
    return PrincipalCredentialSettings.from_env(
        client_id=KEYCLOAK_CLIENT_ID,
        expected_canonical_id=EXPECTED_CANONICAL_ID,
        vault_secret_name="rate-mcp-svc-client-secret",
        inventory_path=INVENTORY_PATH,
    ).client_secret.get_secret_value()


def rate_api_key() -> str:
    env_key = os.environ.get("RATE_API_KEY")
    if env_key:
        return env_key
    try:
        return SecretsClient("dev", inventory_path=INVENTORY_PATH).get("rate-api-key")
    except Exception as exc:
        raise CredentialUnavailableError(
            "rate-api-key is not available: RATE_API_KEY is unset and Vault could not supply it."
        ) from exc


def resolver() -> EnvironmentServiceResolver:
    """This service's only downstream business-API dependency. ServiceResolver
    is env-backed today; a future registry-backed resolver replaces only
    this construction, not any caller."""
    return EnvironmentServiceResolver({"system.rate": "RATE_API_URL"})


def rate_base_url() -> str:
    try:
        return resolver().resolve("system.rate")
    except Exception:
        return os.environ.get("RATE_URL", "http://127.0.0.1:8005")


def cedar_url() -> str:
    return CedarSettings.from_env().cedar_url
