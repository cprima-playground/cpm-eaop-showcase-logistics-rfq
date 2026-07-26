"""Regression guard: actions removed by an explicit finding must not
silently return through a stale fixture, generated artifact, or a partial
future edit. Reviewed and confirmed missing this round: the earlier
Finding 2 fix removed approval.request's agent OWNERSHIP
(agents/catalog.yaml) but left the action DEFINITION itself in
business/actions.yaml -- now actually removed. Guard against it coming
back without a new ADR reversing Finding 2.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

RFQ_ROOT = Path(__file__).resolve().parents[3]


def test_approval_request_action_stays_removed_from_source():
    doc = yaml.safe_load((RFQ_ROOT / "business" / "actions.yaml").read_text(encoding="utf-8"))
    assert "approval.request" not in doc["actions"], (
        "approval.request reappeared in business/actions.yaml -- Finding 2 "
        "removed it; re-adding it needs a new ADR reversing that decision, "
        "not a silent edit"
    )


def test_approval_request_action_stays_removed_from_committed_schema():
    schema = json.loads((RFQ_ROOT / "authorization" / "agentic.cedarschema").read_text(encoding="utf-8"))
    assert "approval.request" not in schema["Agentic"]["actions"]
