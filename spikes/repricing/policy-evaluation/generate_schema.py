"""Generate the showcase's Cedar schema from the authz projection + authored actions.

Standalone (no cpm-eaop taxonomy dependency, per ADR-001 - this showcase shares no
code with cpm-eaop). Mirrors cpm-eaop tools/generate_cedar_schema.py's shape and
rules: entity types + attributes + `member_of` parents come from the projection;
actions come verbatim from the authored actions file. The projection's `ontology:`
field is informational only here (no external taxonomy to cross-check against).

Run: uv run generate_schema.py
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

RFQ_ROOT = Path(__file__).resolve().parents[3]
PROJECTION = RFQ_ROOT / "authorization" / "authz-projection.yaml"
ACTIONS = RFQ_ROOT / "business" / "actions.yaml"
OUT = RFQ_ROOT / "authorization" / "agentic.cedarschema"


def cedar_type(spec: str) -> dict:
    spec = spec.strip()
    if spec.startswith("Set<") and spec.endswith(">"):
        return {"type": "Set", "element": cedar_type(spec[4:-1])}
    if spec in ("String", "Boolean", "Long"):
        return {"type": spec}
    raise SystemExit(f"unsupported attribute type in projection: {spec!r}")


def attr_entry(value) -> dict:
    if isinstance(value, str):
        return cedar_type(value)
    out = cedar_type(value["type"])
    if value.get("required") is False:
        out["required"] = False
    return out


def main() -> int:
    projection = yaml.safe_load(PROJECTION.read_text(encoding="utf-8"))
    actions_doc = yaml.safe_load(ACTIONS.read_text(encoding="utf-8"))

    ns = projection["namespace"]
    entity_types: dict[str, dict] = {}
    for name, spec in projection["entities"].items():
        spec = spec or {}
        entry: dict = {}
        if spec.get("parents"):
            entry["memberOfTypes"] = list(spec["parents"])
        attrs = spec.get("attributes") or {}
        entry["shape"] = {
            "type": "Record",
            "attributes": {k: attr_entry(v) for k, v in attrs.items()},
        }
        entity_types[name] = entry

    declared = set(projection["entities"])
    actions: dict[str, dict] = {}
    for act, spec in actions_doc["actions"].items():
        for role in ("principals", "resources"):
            for t in spec[role]:
                if t not in declared:
                    raise SystemExit(f"action '{act}': {role} type '{t}' not a projected entity")
        ctx = spec.get("context") or {}
        actions[act] = {
            "appliesTo": {
                "principalTypes": list(spec["principals"]),
                "resourceTypes": list(spec["resources"]),
                "context": {
                    "type": "Record",
                    "attributes": {k: attr_entry(v) for k, v in ctx.items()},
                },
            }
        }

    schema = {ns: {"entityTypes": entity_types, "actions": actions}}
    OUT.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}: {len(entity_types)} entity types, "
          f"{len(actions)} actions (actions authored, not generated)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
