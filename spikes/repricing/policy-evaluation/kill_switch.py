"""Kill switch — a PEP-level pre-check, NOT a Cedar policy.

Per systems/authorization/governance-policies.md: "Runtime enforcement should check
kill-switch state before... executing an MCP tool." This is enforced before Cedar is
even called; a disabled switch short-circuits to deny locally.
"""

from __future__ import annotations

# scope -> target id -> enabled. Empty/missing = enabled (default-on).
_REGISTRY: dict[str, dict[str, bool]] = {
    "platform": {"global-repricing": True},
    "agent": {},
}


def disable_agent(agent_id: str) -> None:
    _REGISTRY["agent"][agent_id] = False


def reset() -> None:
    _REGISTRY["agent"].clear()
    _REGISTRY["platform"]["global-repricing"] = True


def check(principal_id: str) -> bool:
    """True = proceed to Cedar. False = fail closed, do not call Cedar at all."""
    if not _REGISTRY["platform"].get("global-repricing", True):
        return False
    return _REGISTRY["agent"].get(principal_id, True)
