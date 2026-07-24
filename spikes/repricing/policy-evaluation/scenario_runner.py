"""Drive a scenario .yaml's `when` block through the isolated cedar-agent and
return per-action results, ready to assert against the `then` block.

Resources need no /v1/data entry (see entities.py docstring) -- only principals +
groups are loaded as data; resources are referenced purely by typed uid string.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import yaml

import bundle
import entities
import kill_switch

RFQ_ROOT = Path(__file__).resolve().parents[3]
SCENARIOS_DIR = RFQ_ROOT / "scenarios"


def _base_url() -> str:
    return os.environ.get("CEDAR_AGENT_URL", "http://localhost:8280")


def principal_ref(principal_id: str) -> str:
    etype = "AgentPrincipal" if principal_id in entities.AGENT_IDS else "Principal"
    return entities.ref(etype, principal_id)


def resource_ref(resource: str) -> str:
    """Scenario yaml gives resources as 'Type::id' -> Agentic::Type::"id"."""
    etype, _, eid = resource.partition("::")
    return entities.ref(etype, eid)


def load_scenario(name: str) -> dict:
    path = SCENARIOS_DIR / f"{name}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def run_step(step: dict, *, base_url: str | None = None) -> dict:
    """Run one `when` authorization step. Returns {effect, determining, obligations}."""
    principal_id = step["principal"]

    if not kill_switch.check(principal_id):
        return {"effect": "deny", "determining": [], "obligations": [], "reason": "kill-switch"}

    body = {
        "principal": principal_ref(principal_id),
        "action": entities.action_ref(step["action"]),
        "resource": resource_ref(step["resource"]),
        "context": step.get("context") or {},
    }
    url = (base_url or _base_url()) + "/v1/is_authorized"
    r = httpx.post(url, json=body, timeout=10.0)
    r.raise_for_status()
    data = r.json()
    diag = data.get("diagnostics", {})
    effect = "allow" if data.get("decision") == "Allow" else "deny"
    determining = sorted(diag.get("reason", []))
    obligations = sorted(bundle.resolve_obligation_ids(determining)) if effect == "allow" else []
    return {"effect": effect, "determining": determining, "obligations": obligations}


def run_scenario(name: str, *, base_url: str | None = None) -> list[dict]:
    """Run every authorization step in a scenario's `when` block (event-only
    steps, e.g. quote-status-change, are skipped -- they carry no `action`)."""
    doc = load_scenario(name)
    results = []
    for step in doc["when"]:
        if "action" not in step:
            continue  # a bare business event (status transition), not an authz call
        results.append({"action": step["action"], **run_step(step, base_url=base_url)})
    return results
