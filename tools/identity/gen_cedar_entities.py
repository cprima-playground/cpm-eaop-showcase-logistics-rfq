"""Cedar Entity Gen (M3.5). Consumes the APPROVED Validated Identity Model
(post STOP-AND-REVIEW) + agents/catalog.yaml's can_call graph, produces Cedar
entity data loadable via rfq_common.pdp.DataAdmin.

Non-inference invariant (implementation plan, M3.5 acceptance criterion):
this module generates identity/group/agent-relationship entities ONLY --
Human/Agent/Workload/Group instances and the can_call projection. It MUST
NOT synthesize business-resource instances (RFQ, Quote, CarrierRate,
Booking, ...) -- those are runtime SoR facts, never identity-pipeline output.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from tools.identity.validator import CanonicalPrincipal, ValidatedIdentityModel


class CedarEntityGenError(Exception):
    pass


def _catalog_id_to_canonical(catalog_id: str) -> str:
    """agents/catalog.yaml uses bare ids like 'lane-evaluation-agent';
    identity/actors.yaml uses 'agent.lane-evaluation'. Fixed suffix-strip
    convention -- fail loud on anything that doesn't follow it, not a
    silent best-effort guess."""
    suffix = "-agent"
    if not catalog_id.endswith(suffix):
        raise CedarEntityGenError(f"catalog agent id {catalog_id!r} does not end with {suffix!r}")
    return "agent." + catalog_id[: -len(suffix)]


def _load_can_call_by_canonical_id(catalog_path: Path) -> dict[str, list[str]]:
    doc = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}
    result: dict[str, list[str]] = {}
    for agent in doc.get("agents", []):
        canonical = _catalog_id_to_canonical(agent["id"])
        callees = agent.get("caller_identity", {}).get("can_call", [])
        result[canonical] = [_catalog_id_to_canonical(c) for c in callees]
    return result


def _load_delegatable_actions_by_canonical_id(catalog_path: Path) -> dict[str, list[str]]:
    """M4a second checkpoint: an agent's delegatable_actions == its own
    owned_actions (agents/catalog.yaml) -- no narrower delegation scope is
    modeled yet, see authz-projection.yaml's attribute comment."""
    doc = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}
    return {
        _catalog_id_to_canonical(agent["id"]): list(agent.get("owned_actions", []))
        for agent in doc.get("agents", [])
    }


def _uid(entity_type: str, entity_id: str) -> dict[str, Any]:
    """Mirrors rfq_common.pdp.entities.uid()'s output shape exactly (not
    imported -- tools/identity has no dependency on the rfq_common package,
    keeping it runnable via `uv run --with pydantic --with pyyaml`)."""
    return {"type": f"Agentic::{entity_type}", "id": entity_id}


def _principal_entity(
    p: CanonicalPrincipal,
    can_call_by_id: dict[str, list[str]],
    delegatable_actions_by_id: dict[str, list[str]],
) -> dict[str, Any]:
    parents = [_uid("Group", g) for g in p.member_of]

    if p.kind == "human":
        attrs: dict[str, Any] = {"kind": "human", "active": True}
        return {"uid": _uid("Principal", p.id), "attrs": attrs, "parents": parents}

    if p.kind == "agent":
        attrs = {
            "kind": "agent",
            "active": True,
            "canonical_id": p.id,
            "can_call": can_call_by_id.get(p.id, []),
            "delegatable_actions": delegatable_actions_by_id.get(p.id, []),
        }
        if p.trust_domain is not None:
            attrs["trust_domain"] = p.trust_domain
        return {"uid": _uid("AgentPrincipal", p.id), "attrs": attrs, "parents": parents}

    if p.kind == "workload":
        if p.system is None:
            raise CedarEntityGenError(f"workload {p.id!r} has no system")
        attrs = {"kind": "workload", "active": True, "system": p.system}
        if p.trust_domain is not None:
            attrs["trust_domain"] = p.trust_domain
        return {"uid": _uid("Workload", p.id), "attrs": attrs, "parents": []}

    raise CedarEntityGenError(f"unhandled kind {p.kind!r} for actor {p.id!r}")


def generate_cedar_entities(model: ValidatedIdentityModel, catalog_path: Path) -> list[dict[str, Any]]:
    can_call_by_id = _load_can_call_by_canonical_id(catalog_path)
    delegatable_actions_by_id = _load_delegatable_actions_by_canonical_id(catalog_path)

    entities = [{"uid": _uid("Group", g.group_id), "attrs": {}, "parents": []} for g in model.groups]
    entities += [_principal_entity(p, can_call_by_id, delegatable_actions_by_id) for p in model.principals]
    return entities
