"""Claims -> Principal resolution (identity/claims-contract.md), mirroring
cpm-eaop's src/spike/model/identity.py::resolve_principal.

Minimal on purpose: only the HUMAN path is implemented (this is the first
thing in RfQ to do a human SSO login at all -- the ops-dashboard). The
agent-kind branch (azp checked against agents/catalog.yaml) is NOT
implemented -- no agent authenticates via SSO here, only via
client-credentials (a separate, already-proven path). A caller that isn't
human resolves to kind="service", not "agent" -- narrower than the full
contract, sufficient for what actually calls this today.

HARD RULE (identity/README.md): `roles` here is a Keycloak client-role
claim (qms-web's UI-gating roles -- reader/commercial-manager/pricing-
manager/administrator, see infra/keycloak/terraform/keycloak-qms.tf's
header comment) -- application-local UI entitlement, NOT a canonical
authorization fact. Cedar authorizes on canonical principal id + GROUP
membership (Agentic::Group::"rfq-commercial-emea"), never on this field.
Do not use `Principal.roles`/`has_role()` for an authorization decision
anywhere in the request path -- that would silently reintroduce the
Keycloak-role-as-authorization-model this project deliberately separated
out. UI-gating ("does this session show the approve button") is the only
legitimate use.
"""

from __future__ import annotations

from pydantic import BaseModel


class Principal(BaseModel):
    kind: str  # "human" | "service"
    id: str
    oid: str | None = None
    tid: str | None = None
    groups: list[str] | None = None
    roles: list[str] | None = None
    active: bool = True
    # QMS-specific custom claims (keycloak-qms.tf's approval_limit_eur_cents/
    # manager user-attribute mappers) -- optional on every other principal,
    # only ever populated for QMS's own login. Kept here rather than a
    # generic attributes bag: these two are the only custom claims any
    # system currently emits, and typed fields catch a typo/rename at
    # attribute-access time instead of silently returning None from a dict.
    manager: str | None = None
    approval_limit_eur_cents: int | None = None

    def has_role(self, role: str) -> bool:
        """UI-gating only ("does this session show the approve button") --
        NEVER an authorization check. See module docstring's HARD RULE."""
        return self.roles is not None and role in self.roles


def _canonical_human_id(claims: dict) -> str:
    """`sub` is NOT a stable, readable canonical id for a human on either
    provider -- Keycloak's `sub` is its own internal user UUID; Entra v2
    tokens default to a "pairwise" `sub`, a privacy-preserving identifier
    opaque per (app, tenant). Verified against REAL tokens from both IdPs
    for the same human (M7 live-login checkpoint): neither `sub` matched
    identity/actors.yaml's canonical id ("diane.delgado") -- this was
    silently unverified before (no existing test asserted `Principal.id`,
    only role/group/manager fields), and load-bearing: mock_qms's real
    SSO-authenticated approve/reject button (api.py's
    ui_decide_quote_version) stores this id as a QuoteDecision's
    `approver` -- was recording an unreadable, non-canonical UUID on
    every real human decision.

    `preferred_username` IS the canonical id on both providers: Keycloak
    emits it bare ("diane.delgado"); Entra emits it as a UPN
    ("diane.delgado@rpapubhotmail.onmicrosoft.com") -- stripping the
    domain suffix, when present, unifies both without a provider branch.
    Falls back to `sub` only if `preferred_username` is absent entirely
    (defensive, not expected on any real token this repo issues)."""
    preferred_username = claims.get("preferred_username") or claims.get("upn")
    if preferred_username:
        return preferred_username.split("@", 1)[0]
    return claims.get("sub", "")


def resolve_principal(claims: dict) -> Principal:
    is_human = any(k in claims for k in ("tid", "oid", "groups"))
    kind = "human" if is_human else "service"

    approval_limit = claims.get("approval_limit_eur_cents") if is_human else None
    return Principal(
        kind=kind,
        id=_canonical_human_id(claims) if is_human else claims.get("sub", ""),
        oid=claims.get("oid") if is_human else None,
        tid=claims.get("tid") if is_human else None,
        groups=claims.get("groups") if is_human else None,
        roles=claims.get("roles") if is_human else None,
        active=claims.get("active", True),
        manager=claims.get("manager") if is_human else None,
        approval_limit_eur_cents=int(approval_limit) if approval_limit is not None else None,
    )
