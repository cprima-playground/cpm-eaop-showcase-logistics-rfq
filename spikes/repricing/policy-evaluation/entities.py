"""Cedar entity refs + static entity data for the RfQ repricing scenarios.

Mirrors cpm-eaop src/spike/model/entities.py's ref-building shape. Resources need
NO /v1/data entry for these policies: every condition in policies.cedar reads only
context.* and principal.*/group-membership, never a resource attribute. So only
principals + groups are loaded as data; resources are referenced purely by typed
uid string in the request.
"""

from __future__ import annotations

NS = "Agentic"


def ref(etype: str, eid: str) -> str:
    return f'{NS}::{etype}::"{eid}"'


def action_ref(action: str) -> str:
    return f'{NS}::Action::"{action}"'


def uid(etype: str, eid: str) -> dict:
    return {"type": f"{NS}::{etype}", "id": eid}


# --- static principals + groups (the three agents, the human, her group) ------

AGENT_IDS = [
    "lane-evaluation-agent",
    "commercial-normalization-agent",
    "route-decision-agent",
]

HUMAN_GROUP = "rfq-commercial-emea"


def agent_entity(agent_id: str, *, active: bool = True) -> dict:
    return {
        "uid": uid("AgentPrincipal", agent_id),
        "attrs": {"kind": "agent", "active": active, "trust_domain": "internal"},
        "parents": [],
    }


def human_entity(human_id: str, *, active: bool = True, group: str = HUMAN_GROUP) -> dict:
    return {
        "uid": uid("Principal", human_id),
        "attrs": {"kind": "human", "active": active},
        "parents": [uid("Group", group)],
    }


def group_entity(group_id: str) -> dict:
    return {"uid": uid("Group", group_id), "attrs": {}, "parents": []}


def static_entities() -> list[dict]:
    """The baseline entity set every scenario needs: 3 active agents, one active
    human in her group. Failure-injection tests build their own variants inline."""
    entities = [agent_entity(a) for a in AGENT_IDS]
    entities.append(human_entity("mona.commercial"))
    entities.append(group_entity(HUMAN_GROUP))
    return entities
