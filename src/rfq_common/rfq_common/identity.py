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


def resolve_principal(claims: dict) -> Principal:
    is_human = any(k in claims for k in ("tid", "oid", "groups"))
    kind = "human" if is_human else "service"

    approval_limit = claims.get("approval_limit_eur_cents") if is_human else None
    return Principal(
        kind=kind,
        id=claims.get("sub", ""),
        oid=claims.get("oid") if is_human else None,
        tid=claims.get("tid") if is_human else None,
        groups=claims.get("groups") if is_human else None,
        roles=claims.get("roles") if is_human else None,
        active=claims.get("active", True),
        manager=claims.get("manager") if is_human else None,
        approval_limit_eur_cents=int(approval_limit) if approval_limit is not None else None,
    )
