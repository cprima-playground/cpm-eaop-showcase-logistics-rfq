"""M5.5: runtime service descriptor (tmp/RuntimeConfigurationContract
ServiceRegistryFoundation.md #5) -- a projection, NOT a new source of
truth. Every independently deployable A2A agent / MCP server exposes the
same machine-readable descriptor shape at GET /descriptor, built from:

  canonical identity + agents/catalog.yaml / interfaces/mcp/tools.yaml
      -> canonical_id, skills/tools (never hand-duplicated)
  runtime configuration (rfq_common.settings)
      -> base_url, instance_id, dependency endpoints
  authenticated identity (rfq_common.pep.preflight)
      -> the startup self-check this module also provides

Hard invariants (enforced by construction, not by convention):
  - secrets/tokens/credentials NEVER appear on the descriptor
  - request-scoped provenance (correlation_id, root_requester, ...)
    NEVER appears
  - the service FAILS STARTUP if its authenticated identity disagrees
    with its declared canonical_id -- see run_startup_self_check

This module does NOT build a service registry. It only makes the later
"REGISTER this descriptor somewhere" step cheap -- deferred, explicitly,
per the plan.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from rfq_common.pep.preflight import MachineIdentity, PreflightResult, preflight_machine_identity

logger = logging.getLogger("rfq_common.descriptor")

# Bump on any breaking change to ServiceDescriptor's shape (field removed,
# renamed, or its meaning changed). 1.0 -> 1.1 (M8): additive only --
# kind gained "control-plane", ProtocolInfo.type gained "rest", for
# mission-control-api, the first real consumer of this schema (there
# were 7 producers and 0 consumers before it). Producers are
# unaffected; a consumer must be written tolerant of unknown kind/
# protocol.type values (controlplane.md's own compatibility rule,
# applied as code here, not just prose) rather than assuming every
# future addition bumps this version. 1.1 -> 1.2 (M10): additive only --
# kind gained "platform", for geo-api -- a real, always-on service that
# is neither an a2a-agent, an mcp-server, nor mission-control's own
# control-plane, so reusing any of those three would misdescribe it.
DESCRIPTOR_SCHEMA_VERSION = "1.2"


class ProtocolInfo(BaseModel):
    type: Literal["a2a", "mcp", "rest"]
    version: str | None = None


class EndpointInfo(BaseModel):
    base_url: str
    health: str = "/healthz"
    protocol: ProtocolInfo


class IdentityInfo(BaseModel):
    expected_canonical_id: str
    trust_domain: str | None = None


class CapabilitiesInfo(BaseModel):
    source: str  # e.g. "agents/catalog.yaml" or "interfaces/mcp/tools.yaml"
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)


class DependencyInfo(BaseModel):
    canonical_id: str
    relation: Literal["a2a", "mcp", "business-api"]
    endpoint: str


class StatusInfo(BaseModel):
    readiness: Literal["ready", "not_ready"] = "ready"


class ServiceDescriptor(BaseModel):
    """`canonical_id` is the LOGICAL/service identity (what a registry's
    RESOLVE would key lookup by -- stable across restarts, deploys, and
    however many instances run); `instance_id` is THIS PROCESS's identity
    (new every boot, per new_instance_id()'s own docstring). A future
    registry keys by canonical_id and may hold multiple live records
    distinguished by instance_id -- the two must never be conflated."""

    schema_version: str = DESCRIPTOR_SCHEMA_VERSION
    canonical_id: str
    kind: Literal["a2a-agent", "mcp-server", "control-plane", "platform"]
    instance_id: str
    endpoints: EndpointInfo
    identity: IdentityInfo
    capabilities: CapabilitiesInfo
    dependencies: list[DependencyInfo] = Field(default_factory=list)
    status: StatusInfo = Field(default_factory=StatusInfo)


def new_instance_id() -> str:
    """One per process lifetime -- call once at import/build time, not
    per request (an instance_id that changed per request wouldn't mean
    "this running process," it would mean nothing)."""
    return str(uuid.uuid4())


def build_descriptor(
    *,
    canonical_id: str,
    kind: Literal["a2a-agent", "mcp-server", "control-plane", "platform"],
    instance_id: str,
    base_url: str,
    protocol_type: Literal["a2a", "mcp", "rest"],
    protocol_version: str | None = None,
    trust_domain: str | None = None,
    capability_source: str,
    skills: list[str] | None = None,
    tools: list[str] | None = None,
    dependencies: list[DependencyInfo] | None = None,
    health_path: str = "/healthz",
) -> ServiceDescriptor:
    return ServiceDescriptor(
        canonical_id=canonical_id,
        kind=kind,
        instance_id=instance_id,
        endpoints=EndpointInfo(
            base_url=base_url, health=health_path,
            protocol=ProtocolInfo(type=protocol_type, version=protocol_version),
        ),
        identity=IdentityInfo(expected_canonical_id=canonical_id, trust_domain=trust_domain),
        capabilities=CapabilitiesInfo(source=capability_source, skills=skills or [], tools=tools or []),
        dependencies=dependencies or [],
    )


async def run_startup_self_check(
    identity: MachineIdentity, *, oidc_issuer_url: str, root: Path,
) -> PreflightResult:
    """OIDC_CLIENT_ID + secret -> Keycloak token -> resolve_principal() ->
    must equal identity.canonical_id, or the process must not finish
    starting. Reuses rfq_common.pep.preflight.preflight_machine_identity
    directly -- the same chain the machine-identity preflight test suite
    already proves, now enforced per real boot instead of only in CI/test
    runs. Turns a stale Vault secret into an immediate, loud startup
    failure instead of a deep-chain 401 discovered mid-request.

    Never logs the token or secret -- only the resolved canonical id."""
    result = await preflight_machine_identity(identity, oidc_issuer_url=oidc_issuer_url, root=root)
    if not result.ok:
        raise RuntimeError(
            f"startup identity self-check failed for {identity.canonical_id}: "
            f"secret_ok={result.secret_ok} grant_ok={result.grant_ok} "
            f"resolves_ok={result.resolves_ok} error={result.error}"
        )
    logger.info("authenticated workload identity: %s", result.resolved_id)
    return result
