"""M6, built directly on M5.5's shared rfq_common.settings contract.
Three downstream credentials, none conflated: qms-mcp's OWN
introspection-auth client secret (OIDC_CLIENT_SECRET); qms-api-key
(transport auth to mock-qms, decision #8's shared-key posture); fx-api-key
(transport auth to mock-fx, same posture -- route-cost.normalize's real
freshness fact comes from there)."""

from __future__ import annotations

import os
from pathlib import Path

from rfq_common.secrets import SecretsClient
from rfq_common.service_resolver import EnvironmentServiceResolver
from rfq_common.settings import CedarSettings, CredentialUnavailableError, PrincipalCredentialSettings, ResourceServerSettings

RFQ_ROOT = Path(__file__).resolve().parents[3]
INVENTORY_PATH = RFQ_ROOT / "identity" / "credentials-inventory.yaml"

KEYCLOAK_CLIENT_ID = "qms-mcp-svc"  # identity/projections/keycloak.yaml: workload.qms-mcp
EXPECTED_CANONICAL_ID = "workload.qms-mcp"


def keycloak_url() -> str:
    return ResourceServerSettings.from_env().keycloak_base_url


def introspection_endpoint() -> str:
    return ResourceServerSettings.from_env().introspection_url


def introspection_client_secret() -> str:
    return PrincipalCredentialSettings.from_env(
        client_id=KEYCLOAK_CLIENT_ID,
        expected_canonical_id=EXPECTED_CANONICAL_ID,
        vault_secret_name="qms-mcp-svc-client-secret",
        inventory_path=INVENTORY_PATH,
    ).client_secret.get_secret_value()


def qms_api_key() -> str:
    env_key = os.environ.get("QMS_API_KEY")
    if env_key:
        return env_key
    try:
        return SecretsClient("dev", inventory_path=INVENTORY_PATH).get("qms-api-key")
    except Exception as exc:
        raise CredentialUnavailableError(
            "qms-api-key is not available: QMS_API_KEY is unset and Vault could not supply it."
        ) from exc


def fx_api_key() -> str:
    env_key = os.environ.get("FX_API_KEY")
    if env_key:
        return env_key
    try:
        return SecretsClient("dev", inventory_path=INVENTORY_PATH).get("fx-api-key")
    except Exception as exc:
        raise CredentialUnavailableError(
            "fx-api-key is not available: FX_API_KEY is unset and Vault could not supply it."
        ) from exc


def resolver() -> EnvironmentServiceResolver:
    """This service's downstream business-API dependencies. ServiceResolver
    is env-backed today; a future registry-backed resolver replaces only
    this construction, not any caller."""
    return EnvironmentServiceResolver({"system.qms": "QMS_API_URL", "system.fx": "FX_API_URL"})


def qms_base_url() -> str:
    try:
        return resolver().resolve("system.qms")
    except Exception:
        return os.environ.get("QMS_URL", "http://127.0.0.1:8007")


def fx_base_url() -> str:
    try:
        return resolver().resolve("system.fx")
    except Exception:
        return os.environ.get("FX_URL", "http://127.0.0.1:8001")


def cedar_url() -> str:
    return CedarSettings.from_env().cedar_url
