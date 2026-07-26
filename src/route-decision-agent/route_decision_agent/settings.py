"""M5.5: built on rfq_common.settings's shared composable classes -- same
public functions as before this migration (executor.py/api.py/cli.py
unchanged), now a thin service-specific adapter instead of an
independent implementation. route-decision-agent-svc's ONE Keycloak
client secret does double duty: verifying inbound A2A callers
(introspection) and minting this agent's own outbound token when it
calls lane-evaluation-agent."""

from __future__ import annotations

import os
from pathlib import Path

from rfq_common.service_resolver import EnvironmentServiceResolver
from rfq_common.settings import CedarSettings, CredentialUnavailableError, PrincipalCredentialSettings, ResourceServerSettings

RFQ_ROOT = Path(__file__).resolve().parents[3]
INVENTORY_PATH = RFQ_ROOT / "identity" / "credentials-inventory.yaml"

KEYCLOAK_CLIENT_ID = "route-decision-agent-svc"
EXPECTED_CANONICAL_ID = "agent.route-decision"

__all__ = [
    "CredentialUnavailableError", "oidc_issuer_url", "introspection_endpoint",
    "token_endpoint", "client_secret", "lane_evaluation_agent_url", "cedar_url",
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
        vault_secret_name="route-decision-agent-client-secret",
        legacy_secret_env_names=("ROUTE_DECISION_AGENT_SECRET",),
        inventory_path=INVENTORY_PATH,
    ).client_secret.get_secret_value()


def resolver() -> EnvironmentServiceResolver:
    return EnvironmentServiceResolver({"agent.lane-evaluation": "LANE_EVAL_AGENT_URL"})


def lane_evaluation_agent_url() -> str:
    try:
        return resolver().resolve("agent.lane-evaluation")
    except Exception:
        return os.environ.get("LANE_EVAL_AGENT_URL", "http://127.0.0.1:8204")


def cedar_url() -> str:
    return CedarSettings.from_env().cedar_url
