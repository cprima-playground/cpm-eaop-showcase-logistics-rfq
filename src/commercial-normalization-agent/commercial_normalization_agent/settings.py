"""M5.5: built on rfq_common.settings's shared composable classes -- same
public functions as before this migration (executor.py/api.py/cli.py
unchanged), now a thin service-specific adapter instead of an
independent implementation. commercial-normalization-agent-svc's ONE
Keycloak client secret does double duty: verifying inbound A2A callers
(introspection) and minting this agent's own outbound token when it
calls route-decision-agent."""

from __future__ import annotations

import os
from pathlib import Path

from rfq_common.service_resolver import EnvironmentServiceResolver
from rfq_common.settings import CedarSettings, CredentialUnavailableError, PrincipalCredentialSettings, ResourceServerSettings

RFQ_ROOT = Path(__file__).resolve().parents[3]
INVENTORY_PATH = RFQ_ROOT / "identity" / "credentials-inventory.yaml"

KEYCLOAK_CLIENT_ID = "commercial-normalization-agent-svc"
EXPECTED_CANONICAL_ID = "agent.commercial-normalization"

__all__ = [
    "CredentialUnavailableError", "oidc_issuer_url", "introspection_endpoint",
    "token_endpoint", "client_secret", "route_decision_agent_url", "cedar_url",
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
        vault_secret_name="commercial-normalization-agent-client-secret",
        legacy_secret_env_names=("COMMERCIAL_NORM_AGENT_SECRET",),
        inventory_path=INVENTORY_PATH,
    ).client_secret.get_secret_value()


def resolver() -> EnvironmentServiceResolver:
    return EnvironmentServiceResolver({"agent.route-decision": "ROUTE_DECISION_AGENT_URL"})


def route_decision_agent_url() -> str:
    try:
        return resolver().resolve("agent.route-decision")
    except Exception:
        return os.environ.get("ROUTE_DECISION_AGENT_URL", "http://127.0.0.1:8205")


def cedar_url() -> str:
    return CedarSettings.from_env().cedar_url
