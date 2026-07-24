"""Claims -> Principal resolution (identity/claims-contract.md), mirroring
cpm-eaop's src/spike/model/identity.py::resolve_principal.

Minimal on purpose: only the HUMAN path is implemented (this is the first
thing in RfQ to do a human SSO login at all -- the ops-dashboard). The
agent-kind branch (azp checked against agents/catalog.yaml) is NOT
implemented -- no agent authenticates via SSO here, only via
client-credentials (a separate, already-proven path). A caller that isn't
human resolves to kind="service", not "agent" -- narrower than the full
contract, sufficient for what actually calls this today.
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

    def has_role(self, role: str) -> bool:
        return self.roles is not None and role in self.roles


def resolve_principal(claims: dict) -> Principal:
    is_human = any(k in claims for k in ("tid", "oid", "groups"))
    kind = "human" if is_human else "service"

    return Principal(
        kind=kind,
        id=claims.get("sub", ""),
        oid=claims.get("oid") if is_human else None,
        tid=claims.get("tid") if is_human else None,
        groups=claims.get("groups") if is_human else None,
        roles=claims.get("roles") if is_human else None,
        active=claims.get("active", True),
    )
