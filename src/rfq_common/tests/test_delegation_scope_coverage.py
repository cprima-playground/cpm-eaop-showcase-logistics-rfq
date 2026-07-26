"""Review round 2, finding #2: the delegation-scope forbid
(forbid-delegation-outside-scope) is action-specific (route.recommend
only) -- proven for the checkpoint operation, not a reusable invariant by
itself. This module closes the gap the way the review's fallback
suggested (generic Cedar action-name comparison across all actions isn't
straightforward with this schema generator): a structural coverage test.

Convention this test enforces, going forward: every action in
business/actions.yaml that declares a `delegated_by` context field MUST
have a corresponding forbid policy in authorization/policies.cedar naming
that exact action AND referencing `delegatable_actions`. Add a new
delegated action without its own forbid, and this test fails --
"claimed delegation bypasses delegatable_actions" (the review's named
failure mode) becomes a caught regression, not a silent gap.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

RFQ_ROOT = Path(__file__).resolve().parents[3]


def _actions_with_delegated_by_context() -> set[str]:
    doc = yaml.safe_load((RFQ_ROOT / "business" / "actions.yaml").read_text(encoding="utf-8"))
    return {
        name for name, spec in doc["actions"].items()
        if spec and "delegated_by" in (spec.get("context") or {})
    }


def _forbid_blocks_referencing_delegatable_actions() -> list[str]:
    """Cedar policy text blocks that both (a) are a `forbid`, and
    (b) reference `delegatable_actions` -- the delegation-scope-guard
    shape this file's convention requires."""
    text = (RFQ_ROOT / "authorization" / "policies.cedar").read_text(encoding="utf-8")
    blocks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not current and (stripped == "" or stripped.startswith("//")):
            continue
        current.append(line)
        if stripped.endswith(";"):
            blocks.append("\n".join(current))
            current = []
    return [b for b in blocks if re.search(r"\bforbid\s*\(", b) and "delegatable_actions" in b]


def test_every_delegated_by_action_has_a_matching_scope_forbid():
    delegated_actions = _actions_with_delegated_by_context()
    assert delegated_actions, "expected at least one action to declare delegated_by (route.recommend)"

    scope_forbid_blocks = _forbid_blocks_referencing_delegatable_actions()
    assert scope_forbid_blocks, "expected at least one forbid policy referencing delegatable_actions"

    uncovered = []
    for action in delegated_actions:
        matched = any(f'"{action}"' in block for block in scope_forbid_blocks)
        if not matched:
            uncovered.append(action)

    assert not uncovered, (
        f"action(s) {uncovered} declare a delegated_by context field but have no matching "
        "forbid-*-outside-scope policy referencing delegatable_actions -- claimed delegation "
        "would bypass delegatable_actions for these actions. Add a forbid policy naming the "
        "action explicitly (see authorization/policies.cedar's forbid-delegation-outside-scope "
        "for the pattern), or remove delegated_by from its actions.yaml context if delegation "
        "isn't actually supported for it yet."
    )


def test_route_recommend_is_currently_the_only_delegated_action():
    """Documents today's actual scope, not a permanent limit -- update this
    assertion (not delete it) when a second delegated action is added, so
    the change is a deliberate, reviewed diff, not silent scope creep."""
    assert _actions_with_delegated_by_context() == {"route.recommend"}
