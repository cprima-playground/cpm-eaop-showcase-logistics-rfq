"""Keycloak Gen (M3.5). Pure function: Validated Identity Model + Keycloak
projection config -> Terraform input (a plain dict, consumed by M3.2's
for_each-driven .tf refactor -- not applied here, no live Keycloak call).

Output attribute shape (manager/region/approval_limit_eur_cents) matches
what the hand-authored infra/keycloak/terraform/*.tf already issues in real
tokens today (verified against a live-decoded qms-web token during this
session) -- this generator reproduces that shape, not a new one.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import yaml

from tools.identity.validator import CanonicalPrincipal, ValidatedIdentityModel

# oid investigation (M3.2 hybrid-migration review): rfq_common.identity.
# resolve_principal() reads `oid`'s PRESENCE (alongside tid/groups) to
# classify a caller as human vs. service -- the stable subject identifier
# is `sub` (-> Principal.id), not oid's value. The hand-assigned GUIDs in
# keycloak.tf today are inert (never read downstream). So: oid must still
# be EMITTED (needed for classification), but any stable-per-user value
# works -- generated deterministically here (uuid5, not random), not
# sourced from identity/actors.yaml (it's a provider-projection concern,
# not a canonical identity fact).
_OID_NAMESPACE = uuid.UUID("8e41c2b0-0000-4000-9000-000000000000")


def generate_oid(canonical_id: str) -> str:
    return str(uuid.uuid5(_OID_NAMESPACE, canonical_id))


class KeycloakGenError(Exception):
    pass


def user_attributes(p: CanonicalPrincipal, oid_overrides: dict[str, str] | None = None) -> dict[str, Any]:
    oid = (oid_overrides or {}).get(p.id, generate_oid(p.id))
    attrs: dict[str, Any] = {"oid": oid}
    if p.region is not None:
        attrs["region"] = p.region
    if p.manager is not None:
        attrs["manager"] = p.manager
    if p.approval_limit is not None:
        if p.approval_limit.currency != "EUR":
            raise KeycloakGenError(
                f"actor {p.id!r}: approval_limit currency {p.approval_limit.currency!r} "
                "has no known Keycloak attribute mapping (only EUR is)"
            )
        attrs["approval_limit_eur_cents"] = str(p.approval_limit.amount_cents)  # Keycloak attrs are always strings
    return attrs


def _split_name(p: CanonicalPrincipal) -> tuple[str, str]:
    """keycloak_user requires first_name/last_name as separate required
    arguments; identity/actors.yaml only has a single `name` field. Split on
    the first space -- every current human name is exactly 'First Last'."""
    if not p.name:
        raise KeycloakGenError(f"actor {p.id!r}: no `name` to derive first_name/last_name from")
    parts = p.name.split(" ", 1)
    if len(parts) != 2:
        raise KeycloakGenError(f"actor {p.id!r}: name {p.name!r} doesn't split into first/last")
    return parts[0], parts[1]


def generate_keycloak_input(model: ValidatedIdentityModel, projection_path: Path) -> dict[str, Any]:
    projection = yaml.safe_load(projection_path.read_text(encoding="utf-8")) or {}
    client_projection: dict[str, dict] = projection.get("clients", {})
    oid_overrides: dict[str, str] = projection.get("oid_overrides", {})
    email_domain = projection.get("email_domain", "rfq-showcase.dev")

    users = []
    for p in model.principals:
        if p.kind != "human":
            continue
        first_name, last_name = _split_name(p)
        users.append({
            "username": p.id,
            "email": f"{p.id}@{email_domain}",
            "first_name": first_name,
            "last_name": last_name,
            "attributes": user_attributes(p, oid_overrides),
        })

    group_memberships = [
        {"username": p.id, "group_id": g}
        for p in model.principals
        if p.kind == "human"
        for g in p.member_of
    ]

    clients = []
    for p in model.principals:
        if p.kind not in ("agent", "workload"):
            continue
        if p.id not in client_projection:
            raise KeycloakGenError(f"actor {p.id!r} ({p.kind}) has no Keycloak client_id in projection config")
        clients.append({"client_id": client_projection[p.id]["client_id"], "service_account_enabled": True})

    groups = [{"group_id": g.group_id, "path": g.path} for g in model.groups]

    return {
        "realm": projection.get("realm", "rfq"),
        "users": users,
        "groups": groups,
        "group_memberships": group_memberships,
        "clients": clients,
    }
