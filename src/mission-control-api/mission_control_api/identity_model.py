"""M8.5 step 8: GET /api/v1/identities. Thin aggregation over the real
declared identity files -- never a live IdP query, never a Vault read.
No client secret, Vault path, or credential value is ever read by this
module, let alone returned -- only canonical facts and provider CLIENT
IDS (public identifiers, not secrets) from identity/projections/*.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml

RFQ_ROOT = Path(__file__).resolve().parents[3]


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def identities_report(root: Path | None = None) -> dict:
    root = root or RFQ_ROOT
    actors = _load(root / "identity" / "actors.yaml").get("actors", [])
    groups = _load(root / "identity" / "groups.yaml").get("groups", [])
    keycloak_clients = _load(root / "identity" / "projections" / "keycloak.yaml").get("clients", {})
    entra_path = root / "identity" / "projections" / "entra.yaml"
    entra_clients = _load(entra_path).get("clients", {}) if entra_path.exists() else {}
    catalog = _load(root / "agents" / "catalog.yaml").get("agents", [])
    tools_doc = _load(root / "interfaces" / "mcp" / "tools.yaml").get("servers", [])

    principals = []
    for actor in actors:
        canonical_id = actor["id"]
        principals.append({
            "id": canonical_id,
            "kind": actor["kind"],
            "trust_domain": actor.get("trust_domain"),
            "keycloak_client_id": keycloak_clients.get(canonical_id, {}).get("client_id"),
            "entra_client_id": entra_clients.get(canonical_id, {}).get("client_id"),
        })

    agent_profiles = []
    for agent in catalog:
        agent_profiles.append({
            "id": agent["id"],
            "fixture": agent.get("fixture", False),
            "can_call": agent.get("caller_identity", {}).get("can_call", []),
            "owned_actions": agent.get("owned_actions", []),
            "mcp_access": agent.get("mcp_access", []),
            "prohibited_actions": agent.get("prohibited_actions", []),
        })

    mcp_servers = []
    for server in tools_doc:
        mcp_servers.append({
            "id": server["id"],
            "tool_action_map": {t["name"]: t.get("action") for t in server.get("tools", [])},
        })

    return {
        "principals": principals,
        "groups": [{"group_id": g["group_id"], "path": g["path"]} for g in groups],
        "agent_capability_profiles": agent_profiles,
        "mcp_servers": mcp_servers,
    }
