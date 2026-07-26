"""M5.5: built on rfq_common.settings's shared composable classes instead
of hand-rolled keycloak_url()/cedar_url()/client_secret() duplicated per
service. Same public functions as before this migration (api.py/cli.py
are unchanged) -- this file is now a thin, service-specific adapter over
the shared model, not an independent implementation.

Two distinct secrets, still not to be confused (per rfq_common.mcp_auth.
verify's module docstring): tms-mcp's OWN introspection-auth client
secret (OIDC_CLIENT_SECRET / legacy TMS_MCP_CLIENT_SECRET) vs. the
tms-api-key it presents *downstream* to mock-tms (transport auth,
decision #8's accepted shared-key posture for this hop, M6a)."""

from __future__ import annotations

import os
from pathlib import Path

from rfq_common.secrets import SecretsClient
from rfq_common.service_resolver import EnvironmentServiceResolver
from rfq_common.settings import CedarSettings, CredentialUnavailableError, PrincipalCredentialSettings, ResourceServerSettings

RFQ_ROOT = Path(__file__).resolve().parents[3]
INVENTORY_PATH = RFQ_ROOT / "identity" / "credentials-inventory.yaml"

KEYCLOAK_CLIENT_ID = "tms-mcp-svc"  # identity/projections/keycloak.yaml: workload.tms-mcp
EXPECTED_CANONICAL_ID = "workload.tms-mcp"

__all__ = [
    "CredentialUnavailableError", "keycloak_url", "introspection_endpoint",
    "introspection_client_secret", "tms_api_key", "tms_base_url", "cedar_url",
    "KEYCLOAK_CLIENT_ID", "EXPECTED_CANONICAL_ID",
]


def keycloak_url() -> str:
    return ResourceServerSettings.from_env().keycloak_base_url


def introspection_endpoint() -> str:
    return ResourceServerSettings.from_env().introspection_url


def introspection_client_secret() -> str:
    return PrincipalCredentialSettings.from_env(
        client_id=KEYCLOAK_CLIENT_ID,
        expected_canonical_id=EXPECTED_CANONICAL_ID,
        vault_secret_name="tms-mcp-svc-client-secret",
        legacy_secret_env_names=("TMS_MCP_CLIENT_SECRET",),
        inventory_path=INVENTORY_PATH,
    ).client_secret.get_secret_value()


def tms_api_key() -> str:
    env_key = os.environ.get("TMS_API_KEY")
    if env_key:
        return env_key
    try:
        return SecretsClient("dev", inventory_path=INVENTORY_PATH).get("tms-api-key")
    except Exception as exc:
        raise CredentialUnavailableError(
            "tms-api-key is not available: TMS_API_KEY is unset and Vault could not supply it."
        ) from exc


def resolver() -> EnvironmentServiceResolver:
    """This service's only downstream business-API dependency. ServiceResolver
    is env-backed today; a future registry-backed resolver replaces only
    this construction, not any caller."""
    return EnvironmentServiceResolver({"system.tms": "TMS_URL"})


def tms_base_url() -> str:
    try:
        return resolver().resolve("system.tms")
    except Exception:
        return os.environ.get("TMS_URL", "http://127.0.0.1:8004")


def cedar_url() -> str:
    return CedarSettings.from_env().cedar_url
