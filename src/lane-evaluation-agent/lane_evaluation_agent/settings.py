"""M5.5: built on rfq_common.settings's shared composable classes -- same
public functions as before this migration (executor.py/api.py/cli.py
unchanged), now a thin service-specific adapter instead of an
independent implementation. lane-evaluation-agent-svc's ONE Keycloak
client secret does double duty, unchanged: (1) authenticates THIS
server's own token-introspection calls when verifying an incoming A2A
caller's bearer token (resource-server role); (2) mints THIS agent's own
client-credentials token when it calls tms-mcp downstream (caller role)."""

from __future__ import annotations

import os
from pathlib import Path

from rfq_common.service_resolver import EnvironmentServiceResolver
from rfq_common.settings import CedarSettings, CredentialUnavailableError, PrincipalCredentialSettings, ResourceServerSettings

RFQ_ROOT = Path(__file__).resolve().parents[3]
INVENTORY_PATH = RFQ_ROOT / "identity" / "credentials-inventory.yaml"

KEYCLOAK_CLIENT_ID = "lane-evaluation-agent-svc"
EXPECTED_CANONICAL_ID = "agent.lane-evaluation"

__all__ = [
    "CredentialUnavailableError", "oidc_issuer_url", "introspection_endpoint",
    "token_endpoint", "client_secret", "tms_mcp_url", "cedar_url",
    "resolver", "KEYCLOAK_CLIENT_ID", "EXPECTED_CANONICAL_ID",
]


def oidc_issuer_url() -> str:
    return ResourceServerSettings.from_env().oidc_issuer_url


def introspection_endpoint() -> str:
    return ResourceServerSettings.from_env().introspection_url


def token_endpoint() -> str:
    return ResourceServerSettings.from_env().token_endpoint


def client_secret() -> str:
    return PrincipalCredentialSettings.from_env(
        client_id=KEYCLOAK_CLIENT_ID,
        expected_canonical_id=EXPECTED_CANONICAL_ID,
        vault_secret_name="lane-evaluation-agent-client-secret",
        legacy_secret_env_names=("LANE_EVAL_AGENT_SECRET",),
        inventory_path=INVENTORY_PATH,
    ).client_secret.get_secret_value()


def resolver() -> EnvironmentServiceResolver:
    """This agent's only downstream dependency (MCP, not A2A -- see
    executor.py). ServiceResolver is env-backed today; a future registry-
    backed resolver would replace only this construction, not any caller."""
    return EnvironmentServiceResolver({"workload.tms-mcp": "TMS_MCP_URL"})


def tms_mcp_url() -> str:
    try:
        return resolver().resolve("workload.tms-mcp")
    except Exception:
        return os.environ.get("TMS_MCP_URL", "http://127.0.0.1:8104")


def cedar_url() -> str:
    return CedarSettings.from_env().cedar_url
