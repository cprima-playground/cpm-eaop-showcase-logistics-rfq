"""ADR-002's action/resource-disjointness ownership rule (plan decision
#12), checked MECHANICALLY, not by inspection: qms-mcp and approval-mcp
both eventually front mock-qms, so that's only a valid shared-API
arrangement if their EXPOSED tool->action sets (interfaces/mcp/tools.yaml
-- what each SERVER exposes, not agents/catalog.yaml's owned_actions,
which is a different relationship entirely, per the plan's own corrected
wording) are provably disjoint.

Deliberately excludes tools with no `action:` mapping (create_approval_
task, get_approval_status -- both explicitly unmapped today per tools.
yaml's own comments, Finding 2) -- an unmapped tool exposes no Cedar
action at all, so it cannot participate in an action-set intersection
either way.
"""

from __future__ import annotations

from pathlib import Path

import yaml

RFQ_ROOT = Path(__file__).resolve().parents[3]


def _action_set(server_id: str) -> set[str]:
    doc = yaml.safe_load((RFQ_ROOT / "interfaces" / "mcp" / "tools.yaml").read_text(encoding="utf-8"))
    server = next(s for s in doc["servers"] if s["id"] == server_id)
    return {tool["action"] for tool in server["tools"] if "action" in tool}


def test_qms_mcp_and_approval_mcp_action_sets_are_disjoint():
    """The mechanical check ADR-002 requires before two MCP servers may
    share mock-qms as their underlying REST API."""
    qms_actions = _action_set("qms-mcp")
    approval_actions = _action_set("approval-mcp")

    assert qms_actions, "qms-mcp must expose at least one real action"
    assert approval_actions, "approval-mcp must expose at least one real action"
    assert qms_actions.isdisjoint(approval_actions), (
        f"ADR-002 violation: qms-mcp and approval-mcp both target mock-qms but "
        f"share action(s) {qms_actions & approval_actions} -- ownership is no "
        f"longer disjoint at the action/resource level"
    )


def test_qms_mcp_action_set_matches_this_milestones_three_implemented_actions():
    """Documents today's real, implemented action set -- update
    deliberately if qms-mcp gains a 4th action."""
    assert _action_set("qms-mcp") == {"quote-price.calculate", "quote-variance.evaluate", "route-cost.normalize"}


def test_approval_mcp_action_set_excludes_the_unmapped_tools():
    """create_approval_task/get_approval_status carry no `action:` key
    (Finding 2) -- confirms they're excluded from the set this check
    reasons about, not silently miscounted as disjoint by accident."""
    doc = yaml.safe_load((RFQ_ROOT / "interfaces" / "mcp" / "tools.yaml").read_text(encoding="utf-8"))
    approval = next(s for s in doc["servers"] if s["id"] == "approval-mcp")
    tool_names_without_action = {t["name"] for t in approval["tools"] if "action" not in t}
    assert tool_names_without_action == {"create_approval_task", "get_approval_status"}
    assert _action_set("approval-mcp") == {"route-deviation.propose", "route.recommend"}
