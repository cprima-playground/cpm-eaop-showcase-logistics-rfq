"""M8.4 step 7: GET /api/v1/policies and /api/v1/policies/drift.

Drift comparison is ID-ONLY, not content-fingerprint (D10's original
hope) -- verified live against the real running cedar-agent: its
GET /v1/policies re-serializes each policy's Cedar text into its OWN
normalized form (different annotation order, different bracket/quote
encoding for the `when` expression body) rather than echoing the
declared source text verbatim. A raw or whitespace-normalized hash
comparison between the two would flag EVERY policy as "changed" even
when semantically identical -- a 100% false-positive rate, worse than
no check at all. This is stated explicitly in the response (`basis`
field) rather than silently narrowed to look more thorough than it is.

Effect (permit/forbid) is derived by a simple regex on the policy's own
head keyword -- Cedar's own grammar requires the block to start with
exactly one of these two words."""

from __future__ import annotations

import re
from pathlib import Path

import httpx

from rfq_common.pdp import PolicyBundle

RFQ_ROOT = Path(__file__).resolve().parents[3]
POLICIES_PATH = RFQ_ROOT / "authorization" / "policies.cedar"
SCHEMA_PATH = RFQ_ROOT / "authorization" / "agentic.cedarschema"
OBLIGATIONS_PATH = RFQ_ROOT / "authorization" / "obligations.yaml"

_EFFECT_RE = re.compile(r"^\s*(permit|forbid)\s*\(", re.MULTILINE)


def _effect(content: str) -> str:
    m = _EFFECT_RE.search(content)
    return m.group(1) if m else "unknown"


def declared_policies(policies_path: Path | None = None) -> list[dict]:
    bundle = PolicyBundle.from_path(policies_path or POLICIES_PATH)
    return [{"id": p["id"], "effect": _effect(p["content"])} for p in bundle.policies()]


def schema_summary(schema_path: Path | None = None) -> dict:
    import json
    schema = json.loads((schema_path or SCHEMA_PATH).read_text(encoding="utf-8"))
    entity_types = list(schema.get("Agentic", {}).get("entityTypes", {}).keys())
    actions = list(schema.get("Agentic", {}).get("actions", {}).keys())
    return {"entity_type_count": len(entity_types), "action_count": len(actions),
            "entity_types": entity_types, "actions": actions}


def obligation_ids(obligations_path: Path | None = None) -> list[str]:
    import yaml
    doc = yaml.safe_load((obligations_path or OBLIGATIONS_PATH).read_text(encoding="utf-8")) or {}
    return sorted(doc.get("obligations", {}).keys())


def policies_report(policies_path: Path | None = None, schema_path: Path | None = None,
                     obligations_path: Path | None = None) -> dict:
    declared = declared_policies(policies_path)
    return {
        "policies": declared,
        "permit_count": sum(1 for p in declared if p["effect"] == "permit"),
        "forbid_count": sum(1 for p in declared if p["effect"] == "forbid"),
        "schema": schema_summary(schema_path),
        "obligation_ids": obligation_ids(obligations_path),
    }


def policy_drift(cedar_url: str, policies_path: Path | None = None, *, timeout: float = 5.0) -> dict:
    declared_ids = {p["id"] for p in declared_policies(policies_path)}
    try:
        r = httpx.get(f"{cedar_url}/v1/policies", timeout=timeout)
        r.raise_for_status()
        live_ids = {p["id"] for p in r.json()}
        reachable = True
    except Exception as exc:
        return {
            "basis": "id-only comparison (see note); cedar-agent unreachable",
            "reachable": False, "error": str(exc),
            "declared_only": sorted(declared_ids), "live_only": [],
        }
    return {
        "note": (
            "ID-only comparison, not content-fingerprint: cedar-agent's live "
            "GET /v1/policies re-serializes each policy's Cedar text into its "
            "own normalized form, different from the declared source text even "
            "when semantically identical -- a content hash would falsely flag "
            "every policy as changed. A same-id policy with a genuinely edited "
            "condition is NOT detected by this check."
        ),
        "reachable": reachable,
        "declared_only": sorted(declared_ids - live_ids),
        "live_only": sorted(live_ids - declared_ids),
    }
