"""M5.5: shared runtime configuration model (tmp/RuntimeConfigurationContract
ServiceRegistryFoundation.md). Composable settings classes every A2A agent
and MCP server builds its concrete settings from, instead of each package
independently inventing its own `keycloak_url()`/`cedar_url()`/
`client_secret()` functions (4 near-duplicates already existed before this).

Config-category discipline this module enforces (plan's 4-category split):
  1. Canonical/static facts (agent canonical_id, skills, can_call, tool->
     action mappings) -- NEVER read here. They come from agents/catalog.yaml,
     interfaces/mcp/tools.yaml, business/actions.yaml directly, loaded by
     the code that needs them, not passed through env vars or this module.
  2. Deployment/runtime config -- what this module resolves, from env vars.
  3. Secrets -- resolved here only as a fallback when no env var override is
     set, via rfq_common.secrets.SecretsClient (Vault in dev); never hand-
     rolled here.
  4. Request-scoped state (bearer tokens, correlation_id, root_requester,
     parent_task_id, delegated_by, skill/tool input) -- NEVER belongs in any
     class in this module. That's flow state (M4a's established posture),
     not service configuration.

Naming standard (applies to services built after this milestone; the 4
already-built services keep their existing env var names as accepted
aliases below rather than being force-migrated -- real churn without a
real payoff for names that already work and are tested):
  SERVICE_HOST / SERVICE_PORT / SERVICE_PUBLIC_URL
  LOG_LEVEL
  OIDC_ISSUER_URL (canonical; KEYCLOAK_BASE_URL / KEYCLOAK_URL are legacy
    fallback names, still read, not expanded further) / KEYCLOAK_REALM /
    KEYCLOAK_INTROSPECTION_URL
  CEDAR_URL
  OIDC_CLIENT_ID / OIDC_CLIENT_SECRET / EXPECTED_CANONICAL_ID
  *_AGENT_URL / *_MCP_URL / *_API_URL / *_API_KEY
  A2A_REQUEST_TIMEOUT_SECONDS / A2A_TASK_TIMEOUT_SECONDS
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, SecretStr

from rfq_common.secrets import SecretsClient


class CredentialUnavailableError(RuntimeError):
    pass


def env(*names: str, default: str | None = None) -> str | None:
    """First set env var among `names`, in priority order -- lets a new
    canonical name (e.g. SERVICE_HOST) and an existing service's legacy
    name (e.g. A2A_HOST) both resolve the same field without forcing a
    rename of already-working, already-tested deployments."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


class ServiceSettings(BaseModel):
    """Group A: this process's own bind/advertise identity. `public_url`
    is deliberately a full URL, not just a hostname -- bind address !=
    externally advertised address, and that distinction matters
    immediately under Docker (host.docker.internal, service-name DNS,
    etc. all differ from the bind host)."""

    host: str
    port: int
    public_url: str
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, *, default_port: int) -> ServiceSettings:
        host = env("SERVICE_HOST", "A2A_HOST", default="127.0.0.1")
        port = int(env("SERVICE_PORT", "A2A_PORT", default=str(default_port)))
        public_url = env("SERVICE_PUBLIC_URL")
        if not public_url:
            public_host = env("A2A_PUBLIC_HOST", "SERVICE_PUBLIC_HOST", default=host)
            public_url = f"http://{public_host}:{port}"
        return cls(host=host, port=port, public_url=public_url, log_level=env("LOG_LEVEL", default="INFO"))


class ResourceServerSettings(BaseModel):
    """Group B: both A2A servers and MCP servers are protected resource
    servers (they verify an inbound bearer token) -- same shape either way,
    one shared class. `oidc_issuer_url` is the provider-neutral canonical
    field (identity provider is a config swap, not a code change -- see
    tmp/oidc-identity-unification-plan.md): OIDC_ISSUER_URL is read first,
    falling back to the legacy KEYCLOAK_BASE_URL/KEYCLOAK_URL names so
    already-working deployments don't need to change anything. `keycloak_realm`
    stays Keycloak-specific on purpose -- it's only used by `token_endpoint`'s
    `/realms/{realm}/...` construction for the Keycloak human-SSO
    Authorization-Code flow, which remains Keycloak-shaped in dev; an Entra
    deployment doesn't have a "realm" concept and doesn't use this property."""

    oidc_issuer_url: str
    keycloak_realm: str
    introspection_url: str

    @classmethod
    def from_env(cls) -> ResourceServerSettings:
        issuer = env("OIDC_ISSUER_URL", "KEYCLOAK_BASE_URL", "KEYCLOAK_URL", default="http://localhost:8081")
        realm = env("KEYCLOAK_REALM", default="rfq")
        introspection = env(
            "KEYCLOAK_INTROSPECTION_URL",
            default=f"{issuer}/realms/{realm}/protocol/openid-connect/token/introspect",
        )
        return cls(oidc_issuer_url=issuer, keycloak_realm=realm, introspection_url=introspection)

    @property
    def token_endpoint(self) -> str:
        return f"{self.oidc_issuer_url}/realms/{self.keycloak_realm}/protocol/openid-connect/token"


class PrincipalCredentialSettings(BaseModel):
    """Group D: THIS process's own workload/agent identity -- never the
    caller's. `client_secret`: env override (`OIDC_CLIENT_SECRET`, plus
    the identity's own legacy env name) takes priority; Vault is the
    fallback, matching every existing settings.py's `client_secret()`
    behavior. `expected_canonical_id` is an integrity check only (see
    rfq_common.descriptor's startup self-check), never the source of
    identity -- identity is always what token introspection + Cedar's
    real client_id map resolve to."""

    client_id: str
    client_secret: SecretStr
    expected_canonical_id: str

    @classmethod
    def from_env(
        cls,
        *,
        client_id: str,
        expected_canonical_id: str,
        vault_secret_name: str,
        legacy_secret_env_names: tuple[str, ...] = (),
        inventory_path: Path,
    ) -> PrincipalCredentialSettings:
        secret = env("OIDC_CLIENT_SECRET", *legacy_secret_env_names)
        if not secret:
            try:
                secret = SecretsClient("dev", inventory_path=inventory_path).get(vault_secret_name)
            except Exception as exc:
                raise CredentialUnavailableError(
                    f"{vault_secret_name} is not available: no OIDC_CLIENT_SECRET/legacy env "
                    "override set, and Vault could not supply it."
                ) from exc
        return cls(client_id=client_id, client_secret=SecretStr(secret), expected_canonical_id=expected_canonical_id)


class CedarSettings(BaseModel):
    """Group C: one shared name across every PEP (this repo's own cedar-
    agent instance -- deliberately not cpm-eaop's unrelated sidecar, see
    rfq_common.pdp.client's own note on that)."""

    cedar_url: str
    timeout_seconds: float = 5.0

    @classmethod
    def from_env(cls) -> CedarSettings:
        return cls(
            cedar_url=env("CEDAR_URL", default="http://localhost:8280"),
            timeout_seconds=float(env("CEDAR_REQUEST_TIMEOUT_SECONDS", default="5.0")),
        )


class A2AClientSettings(BaseModel):
    """Group D (agents only): outbound A2A call behavior. Deliberately
    minimal -- only the two knobs a real requirement exists for today;
    concurrency/retry knobs stay unadded until a real need shows up
    (plan's own guidance: don't add knobs before they serve a real
    runtime requirement)."""

    request_timeout_seconds: float = 10.0
    task_timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> A2AClientSettings:
        return cls(
            request_timeout_seconds=float(env("A2A_REQUEST_TIMEOUT_SECONDS", default="10.0")),
            task_timeout_seconds=float(env("A2A_TASK_TIMEOUT_SECONDS", default="30.0")),
        )
