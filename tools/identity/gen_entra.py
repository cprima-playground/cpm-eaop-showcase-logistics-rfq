"""Entra Gen (M3.5). Pure function: Validated Identity Model + Entra
projection config -> Terraform input (a plain dict, consumed by M3.3 --
not applied here, no live Entra call). Same custom-attribute shape as
gen_keycloak.py's output, for M3.4's canonical-principal parity check to
compare against.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from tools.identity.gen_keycloak import KeycloakGenError, user_attributes
from tools.identity.validator import ValidatedIdentityModel


class EntraGenError(Exception):
    pass


def generate_entra_input(model: ValidatedIdentityModel, projection_path: Path) -> dict[str, Any]:
    projection = yaml.safe_load(projection_path.read_text(encoding="utf-8")) or {}
    tenant_domain = projection["tenant_domain"]
    app_projection: dict[str, dict] = projection.get("app_registrations", {})

    users = []
    for p in model.principals:
        if p.kind != "human":
            continue
        if not p.name:
            raise EntraGenError(f"actor {p.id!r}: no `name` to derive display_name from")
        try:
            attrs = user_attributes(p)
        except KeycloakGenError as exc:
            raise EntraGenError(str(exc)) from exc
        users.append({"upn": f"{p.id}@{tenant_domain}", "display_name": p.name, "attributes": attrs})

    group_memberships = [
        {"upn": f"{p.id}@{tenant_domain}", "group_id": g}
        for p in model.principals
        if p.kind == "human"
        for g in p.member_of
    ]

    app_registrations = []
    for p in model.principals:
        if p.kind not in ("agent", "workload"):
            continue
        if p.id not in app_projection:
            raise EntraGenError(f"actor {p.id!r} ({p.kind}) has no Entra app registration in projection config")
        app_registrations.append({"display_name": app_projection[p.id]["display_name"]})

    groups = [{"group_id": g.group_id, "path": g.path} for g in model.groups]

    return {
        "tenant_domain": tenant_domain,
        "users": users,
        "groups": groups,
        "group_memberships": group_memberships,
        "app_registrations": app_registrations,
    }
