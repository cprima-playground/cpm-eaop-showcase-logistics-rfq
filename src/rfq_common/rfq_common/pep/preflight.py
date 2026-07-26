"""Machine-identity preflight: cross-cutting control added ahead of M6b,
per direct instruction -- the stale-secret incidents (Vault drifting from
Keycloak's live client secret) recurred enough times across M5/M6a that
credential consistency is now a real architectural test concern, not a
one-off debugging fix each time.

Chain proven per identity, end to end, using ONLY production code paths:

  canonical workload/agent (agents/catalog.yaml, identity/projections/
      keycloak.yaml -- the same data resolve_principal's client_id maps
      already derive from, reused here rather than re-declared)
      -> Vault secret (rfq_common.secrets.SecretsClient, dev store --
         READ ONLY, never falls back to an env var override: this
         preflight exists specifically to catch Vault drift, so it must
         look at exactly what Vault holds, not whatever a test run's
         env happens to inject over it)
      -> Keycloak client-credentials grant (does the stored secret
         actually authenticate? -- the point, not a value comparison)
      -> canonical principal resolution (rfq_common.mcp_auth.
         authenticate_request -- the real introspection+resolve path
         every MCP/A2A boundary in this repo uses, not a reimplementation)

Deliberately does NOT compare secret values against Keycloak's own
client-secret admin API (the earlier, weaker diagnostic used ad hoc while
debugging M5/M6a's drift incidents) -- a value comparison can't
distinguish "Vault is stale" from "the comparison itself is stale/wrong
in some other way" the way an actual failed grant unambiguously can.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel

from rfq_common.mcp_auth import AuthenticationError, authenticate_request, build_token_verifier
from rfq_common.pep.resolve import DEFAULT_ROOT, _client_id_maps
from rfq_common.secrets import SecretsClient

INVENTORY_RELATIVE = Path("identity") / "credentials-inventory.yaml"


class MachineIdentity(BaseModel):
    canonical_id: str
    kind: Literal["agent", "workload"]
    client_id: str
    secret_name: str  # rfq_common.secrets credential name (identity/credentials-inventory.yaml)


class PreflightResult(BaseModel):
    identity: MachineIdentity
    secret_ok: bool = False
    grant_ok: bool = False
    resolves_ok: bool = False
    resolved_id: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.secret_ok and self.grant_ok and self.resolves_ok


def discover_machine_identities(root: Path | None = None) -> list[MachineIdentity]:
    """Every agent + workload the real directory currently declares --
    derived from the SAME client_id maps rfq_common.pep.resolve_principal
    uses (agents/catalog.yaml + identity/projections/keycloak.yaml), so
    this list grows automatically as M6 adds more agents/MCP-server
    workloads, with no separate list to keep in sync by hand.

    Secret-name derivation follows the two conventions already real in
    identity/credentials-inventory.yaml today: agent -> "<catalog-id>-
    client-secret" (catalog id, e.g. "lane-evaluation-agent"); workload ->
    "<client_id>-client-secret" (client_id already includes its own
    "-svc" suffix, e.g. "tms-mcp-svc"). Both are genuinely mechanical
    given data this function already has -- not invented per identity."""
    root = root or DEFAULT_ROOT
    agent_map, workload_map = _client_id_maps(root)

    identities: list[MachineIdentity] = []
    for (_provider, client_id), canonical_id in sorted(agent_map.items()):
        catalog_id = canonical_id.removeprefix("agent.") + "-agent"
        identities.append(MachineIdentity(
            canonical_id=canonical_id, kind="agent", client_id=client_id,
            secret_name=f"{catalog_id}-client-secret",
        ))
    for (_provider, client_id), canonical_id in sorted(workload_map.items()):
        identities.append(MachineIdentity(
            canonical_id=canonical_id, kind="workload", client_id=client_id,
            secret_name=f"{client_id}-client-secret",
        ))
    return identities


async def _client_credentials_token(oidc_issuer_url: str, client_id: str, client_secret: str) -> str | None:
    async with httpx.AsyncClient() as c:
        r = await c.post(
            f"{oidc_issuer_url}/realms/rfq/protocol/openid-connect/token",
            data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
        )
    if r.status_code != 200:
        return None
    return r.json()["access_token"]


async def preflight_machine_identity(
    identity: MachineIdentity, *, oidc_issuer_url: str, root: Path | None = None,
    inventory_path: Path | None = None,
) -> PreflightResult:
    root = root or DEFAULT_ROOT
    inventory_path = inventory_path or (root / INVENTORY_RELATIVE)
    result = PreflightResult(identity=identity)

    try:
        secret = SecretsClient("dev", inventory_path=inventory_path).get(identity.secret_name)
    except Exception as exc:
        result.error = f"secret unavailable: {exc}"
        return result
    result.secret_ok = True

    token = await _client_credentials_token(oidc_issuer_url, identity.client_id, secret)
    if not token:
        result.error = "Keycloak rejected the stored secret's client-credentials grant"
        return result
    result.grant_ok = True

    introspection_endpoint = f"{oidc_issuer_url}/realms/rfq/protocol/openid-connect/token/introspect"
    verifier = build_token_verifier(
        mode="introspection", oidc_issuer_url=oidc_issuer_url,
        introspection_endpoint=introspection_endpoint,
        client_id=identity.client_id, client_secret=secret,
    )
    try:
        resolved = authenticate_request(f"Bearer {token}", verifier=verifier, root=root)
    except AuthenticationError as exc:
        result.error = f"introspection/resolution failed: {exc}"
        return result

    result.resolved_id = resolved.id
    result.resolves_ok = resolved.id == identity.canonical_id
    if not result.resolves_ok:
        result.error = f"resolved to {resolved.id!r}, expected {identity.canonical_id!r}"
    return result
