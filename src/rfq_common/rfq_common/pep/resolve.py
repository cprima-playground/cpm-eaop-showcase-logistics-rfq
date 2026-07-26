"""Token claims -> ResolvedPrincipal. Layer: rfq_common.identity ->
rfq_common.pep (this module) -> MCP servers. Does NOT import rfq_common.pdp
(that's enforce.py's job) and does NOT know about any individual business
system (QMS/TMS/etc.) -- only reads identity/projections/keycloak.yaml and
agents/catalog.yaml, both generic identity-registry data, not application code.

Implements 3 of decision #2's 4 cases (human/agent/workload -- token-shape
classification). The 4th ("workload acting on behalf of an initiating
caller") is not a resolve_principal branch: the caller's own token is
resolved normally as their principal type; the executing workload is
attached separately as Cedar context by enforce.py's caller, never
substituted as the principal (ADR-001 decision #3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from rfq_common.identity import resolve_principal as resolve_human_claims

DEFAULT_ROOT = Path(__file__).resolve().parents[4]


class ResolvedPrincipal(BaseModel):
    kind: Literal["human", "agent", "workload"]
    id: str  # canonical id: "mona.commercial" / "agent.lane-evaluation" / "workload.tms-mcp"
    groups: list[str] = []
    trust_domain: str | None = None
    manager: str | None = None
    approval_limit_eur_cents: int | None = None
    # Auditability (per review): which provider actually authenticated this
    # caller, and what the raw claims' issuer said -- not business state,
    # just enough for an audit record to answer "who authenticated this."
    provider: Literal["keycloak", "entra"] | None = None
    issuer: str | None = None


class PrincipalResolutionError(Exception):
    pass


class ClientIdCollisionError(Exception):
    """Two different canonical ids both map to the same (provider, client_id)
    key -- a real provisioning error, never silently papered over with
    last-write-wins."""
    pass


def _client_id_maps(root: Path) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], str]]:
    """((provider, client_id) -> canonical id) for agents and workloads.
    Keyed by (provider, client_id), not bare client_id -- client ids are
    NOT unique across independent issuers (Keycloak and Entra could,
    implausibly but possibly, reuse the same string), so the provider is
    part of the identity, not an afterthought (tmp/oidc-identity-unification-plan.md)."""
    agent_map: dict[tuple[str, str], str] = {}
    workload_map: dict[tuple[str, str], str] = {}

    def _put(mapping: dict[tuple[str, str], str], key: tuple[str, str], canonical_id: str) -> None:
        existing = mapping.get(key)
        if existing is not None and existing != canonical_id:
            raise ClientIdCollisionError(
                f"client_id {key[1]!r} (provider={key[0]!r}) maps to both "
                f"{existing!r} and {canonical_id!r} -- a real provisioning "
                f"error, not resolvable by last-write-wins"
            )
        mapping[key] = canonical_id

    catalog = yaml.safe_load((root / "agents" / "catalog.yaml").read_text(encoding="utf-8"))["agents"]
    for a in catalog:
        canonical_id = "agent." + a["id"].removesuffix("-agent")
        _put(agent_map, ("keycloak", a["caller_identity"]["oidc_client_id"]), canonical_id)

    keycloak_projection = yaml.safe_load(
        (root / "identity" / "projections" / "keycloak.yaml").read_text(encoding="utf-8")
    )
    for canonical_id, cfg in keycloak_projection.get("clients", {}).items():
        if canonical_id.startswith("workload."):
            _put(workload_map, ("keycloak", cfg["client_id"]), canonical_id)

    entra_projection_path = root / "identity" / "projections" / "entra.yaml"
    if entra_projection_path.exists():
        entra_projection = yaml.safe_load(entra_projection_path.read_text(encoding="utf-8"))
        for canonical_id, cfg in entra_projection.get("clients", {}).items():
            if canonical_id.startswith("agent."):
                _put(agent_map, ("entra", cfg["client_id"]), canonical_id)
            elif canonical_id.startswith("workload."):
                _put(workload_map, ("entra", cfg["client_id"]), canonical_id)

    return agent_map, workload_map


def _trust_domains_by_canonical_id(root: Path) -> dict[str, str]:
    """identity/actors.yaml is the canonical source for trust_domain (already
    a real per-actor field, decision #11) -- read it here instead of
    hardcoding "internal", so an agent/workload principal's trust_domain
    reflects what's actually declared, not a constant every principal shares
    regardless of its real data."""
    actors = yaml.safe_load((root / "identity" / "actors.yaml").read_text(encoding="utf-8"))["actors"]
    return {a["id"]: a["trust_domain"] for a in actors if "trust_domain" in a}


def _provider_from_issuer(issuer: str | None) -> Literal["keycloak", "entra"] | None:
    """Verified against a REAL Entra client-credentials token during this
    pass (tmp/oidc-identity-unification-plan.md): an app registration
    without `api { requested_access_token_version = 2 }` issues a v1.0
    token with issuer `https://sts.windows.net/{tenant}/`, NOT
    `login.microsoftonline.com` -- the string this function originally
    only checked for. Both shapes are matched now; requiring every app
    registration to be reconfigured for v2 tokens just to be recognized
    would be more fragile than handling what Entra actually produces."""
    if issuer is None:
        return None
    if "microsoftonline.com" in issuer or "onmicrosoft.com" in issuer or "sts.windows.net" in issuer:
        return "entra"
    return "keycloak"


def resolve_principal(claims: dict, *, root: Path | None = None) -> ResolvedPrincipal:
    """claims: a verified JWT's claim set (verification itself is out of
    scope here -- see spikes/mcp/authenticated-server's introspection
    pattern for that; this function only classifies+maps already-trusted
    claims)."""
    root = root or DEFAULT_ROOT
    agent_map, workload_map = _client_id_maps(root)
    trust_domains = _trust_domains_by_canonical_id(root)
    provider = _provider_from_issuer(claims.get("iss"))

    # azp (OIDC-standard, Keycloak + Entra v2 tokens) or appid (Entra v1.0
    # tokens -- verified against a real client-credentials token during
    # this pass: no `azp` claim at all without `requested_access_token_
    # version = 2` on the app registration). Checked BEFORE the is_human
    # branch below on purpose -- a v1 Entra app-only token also carries
    # tid/oid (oid == sub for app-only), which would otherwise misclassify
    # a workload/agent as human (claims-contract.md's documented "app-only
    # detection" concern, now empirically confirmed, not just theoretical).
    azp = claims.get("azp") or claims.get("appid")
    lookup_key = (provider, azp)
    if lookup_key in agent_map:
        canonical_id = agent_map[lookup_key]
        return ResolvedPrincipal(kind="agent", id=canonical_id, trust_domain=trust_domains.get(canonical_id),
                                  provider=provider, issuer=claims.get("iss"))
    if lookup_key in workload_map:
        canonical_id = workload_map[lookup_key]
        return ResolvedPrincipal(kind="workload", id=canonical_id, trust_domain=trust_domains.get(canonical_id),
                                  provider=provider, issuer=claims.get("iss"))

    is_human = any(k in claims for k in ("tid", "oid", "groups"))
    if is_human:
        # rfq_common.identity.resolve_principal() (resolve_human_claims)
        # derives the canonical id from `preferred_username`, not `sub` --
        # see its own docstring for why (verified against real tokens
        # from both IdPs, M7 live-login checkpoint) -- correct for both
        # providers already, no provider branch needed here.
        human = resolve_human_claims(claims)
        return ResolvedPrincipal(
            kind="human", id=human.id, groups=human.groups or [],
            manager=human.manager, approval_limit_eur_cents=human.approval_limit_eur_cents,
            provider=provider, issuer=claims.get("iss"),
        )

    raise PrincipalResolutionError(
        f"cannot classify claims as human/agent/workload: azp={azp!r}, "
        f"no tid/oid/groups present"
    )
