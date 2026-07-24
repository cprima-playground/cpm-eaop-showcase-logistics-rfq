"""Identity models -- mirror identity/claims-contract.md (the IdP-agnostic
claim contract, same shape as cpm-eaop InternalPrincipal)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PrincipalKind = Literal["human", "service", "agent", "workload", "external"]


class InternalPrincipal(BaseModel):
    """The IdP-agnostic principal, resolved from any IdP's claims (claims-contract.md)."""

    id: str
    kind: PrincipalKind
    active: bool = True
    scope: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    member_of: list[str] = Field(default_factory=list)
    trust_domain: str | None = None
    department: str | None = None
    business_unit: str | None = None
    azp: str | None = None
    attributes: dict = Field(default_factory=dict)
