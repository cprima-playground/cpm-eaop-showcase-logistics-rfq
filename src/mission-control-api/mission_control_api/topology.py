"""M8.2 step 5: GET /api/v1/topology. TWO SEPARATE, labeled edge layers --
never merged into one graph, because they answer different questions and
come from different authorities:

  runtime-dependency  -- ServiceDescriptor.dependencies, what each live
      service actually reports calling right now (agent-to-agent A2A,
      agent-to-MCP, MCP-to-business-API)
  credential           -- data/identity/machine-identity-inventory.yaml,
      the generated auth-edge inventory (M6 decision #8): who
      authenticates to whom, and how

Neither layer implies authorization -- "discoverable != authorized"
(M5.5's own invariant, restated here at the API level): Cedar, not this
endpoint, answers whether a caller may actually use an edge it can see.

The two layers use different naming schemes (canonical_id vs. bare
service/system names) -- `_normalize()` maps both onto a common
(caller, target) key ONLY for the `unmatched` comparison; the raw,
un-normalized edges are still returned per-layer untouched."""

from __future__ import annotations

from pathlib import Path

import yaml

from .registry import ObservedServiceRegistry

RFQ_ROOT = Path(__file__).resolve().parents[3]
INVENTORY_PATH = RFQ_ROOT / "data" / "identity" / "machine-identity-inventory.yaml"


def _normalize(name: str) -> str:
    """Best-effort common key for cross-layer comparison only. Strips
    canonical_id prefixes (workload./agent./system.) and the mock-*
    convention, so "workload.tms-mcp" and "tms-mcp" and "system.tms"
    and "mock-tms" all become comparable -- imperfect (e.g. "tms-mcp"
    vs "tms" won't unify), which is exactly why `unmatched` is reported
    as a diagnostic, not silently reconciled."""
    for prefix in ("workload.", "agent.", "system."):
        if name.startswith(prefix):
            return name[len(prefix):]
    if name.startswith("mock-"):
        return name[len("mock-"):]
    return name


def runtime_dependency_edges(registry: ObservedServiceRegistry) -> list[dict]:
    edges = []
    for entry in registry.list_entries():
        if entry.descriptor is None:
            continue
        for dep in entry.descriptor.get("dependencies", []):
            edges.append({
                "layer": "runtime-dependency",
                "from": entry.canonical_id,
                "to": dep["canonical_id"],
                "relation": dep["relation"],
                "endpoint": dep["endpoint"],
            })
    return edges


def credential_edges(inventory_path: Path | None = None) -> list[dict]:
    inventory_path = inventory_path or INVENTORY_PATH
    doc = yaml.safe_load(inventory_path.read_text(encoding="utf-8")) or {}
    return [
        {
            "layer": "credential",
            "from": e["caller"],
            "to": e["target"],
            "mechanism": e["mechanism"],
            "status": e["status"],
        }
        for e in doc.get("edges", [])
    ]


def topology(registry: ObservedServiceRegistry, inventory_path: Path | None = None) -> dict:
    runtime = runtime_dependency_edges(registry)
    credential = credential_edges(inventory_path)

    runtime_keys = {(_normalize(e["from"]), _normalize(e["to"])) for e in runtime}
    credential_keys = {(_normalize(e["from"]), _normalize(e["to"])) for e in credential}

    return {
        "note": (
            "Two separate layers, never merged -- neither implies authorization "
            "(discoverable != authorized; Cedar alone answers 'may'). "
            "'unmatched' is a best-effort cross-layer diagnostic (name "
            "normalization is imperfect), not a claim of drift."
        ),
        "runtime_dependency_edges": runtime,
        "credential_edges": credential,
        "unmatched": {
            "runtime_only": sorted([f"{f}->{t}" for f, t in (runtime_keys - credential_keys)]),
            "credential_only": sorted([f"{f}->{t}" for f, t in (credential_keys - runtime_keys)]),
        },
    }
