"""Generate a Cedar JSON schema from a projection dict + an actions dict. Pure
function of already-loaded YAML -- callers own reading authz-projection.yaml /
actions.yaml from wherever their package keeps them. Mirrors cpm-eaop
tools/generate_cedar_schema.py's rules: entity types + attributes + `member_of`
parents from the projection; actions verbatim from the authored actions dict.
The ontology (if any) never contributes actions."""

from __future__ import annotations


def _cedar_type(spec: str) -> dict:
    spec = spec.strip()
    if spec.startswith("Set<") and spec.endswith(">"):
        return {"type": "Set", "element": _cedar_type(spec[4:-1])}
    if spec in ("String", "Boolean", "Long"):
        return {"type": spec}
    raise ValueError(f"unsupported attribute type in projection: {spec!r}")


def _attr_entry(value) -> dict:
    if isinstance(value, str):
        return _cedar_type(value)
    out = _cedar_type(value["type"])
    if value.get("required") is False:
        out["required"] = False
    return out


def generate_schema(projection: dict, actions_doc: dict) -> dict:
    """projection: parsed authz-projection.yaml. actions_doc: parsed actions.yaml.
    Returns the Cedar JSON schema dict, ready to PUT to /v1/schema."""
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
            "attributes": {k: _attr_entry(v) for k, v in attrs.items()},
        }
        entity_types[name] = entry

    declared = set(projection["entities"])
    actions: dict[str, dict] = {}
    for act, spec in actions_doc["actions"].items():
        for role in ("principals", "resources"):
            for t in spec[role]:
                if t not in declared:
                    raise ValueError(f"action '{act}': {role} type '{t}' not a projected entity")
        ctx = spec.get("context") or {}
        actions[act] = {
            "appliesTo": {
                "principalTypes": list(spec["principals"]),
                "resourceTypes": list(spec["resources"]),
                "context": {
                    "type": "Record",
                    "attributes": {k: _attr_entry(v) for k, v in ctx.items()},
                },
            }
        }

    return {ns: {"entityTypes": entity_types, "actions": actions}}
