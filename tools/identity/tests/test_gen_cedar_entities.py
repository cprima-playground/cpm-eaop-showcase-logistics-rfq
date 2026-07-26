from pathlib import Path

import pytest
import yaml

from tools.identity.gen_cedar_entities import CedarEntityGenError, generate_cedar_entities
from tools.identity.validator import validate_identity

ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "agents" / "catalog.yaml"


def _real_model():
    return validate_identity(
        ROOT / "identity" / "actors.yaml",
        ROOT / "identity" / "groups.yaml",
        ROOT / "business" / "departments.yaml",
        ROOT / "business" / "job-titles.yaml",
    )


def test_generates_one_entity_per_principal_plus_groups():
    model = _real_model()
    entities = generate_cedar_entities(model, CATALOG_PATH)
    assert len(entities) == len(model.principals) + len(model.groups)


def test_agent_entities_carry_canonical_id_and_can_call():
    model = _real_model()
    entities = generate_cedar_entities(model, CATALOG_PATH)
    by_uid = {(e["uid"]["type"], e["uid"]["id"]): e for e in entities}

    lane = by_uid[("Agentic::AgentPrincipal", "agent.lane-evaluation")]
    assert lane["attrs"]["canonical_id"] == "agent.lane-evaluation"
    assert lane["attrs"]["can_call"] == ["agent.commercial-normalization"]

    route_decision = by_uid[("Agentic::AgentPrincipal", "agent.route-decision")]
    assert route_decision["attrs"]["can_call"] == ["agent.lane-evaluation"]  # M5a real A2A edge


def test_workload_entities_have_no_parents():
    model = _real_model()
    entities = generate_cedar_entities(model, CATALOG_PATH)
    workloads = [e for e in entities if e["uid"]["type"] == "Agentic::Workload"]
    assert len(workloads) == 4
    assert all(w["parents"] == [] for w in workloads)


def test_human_entities_carry_group_parents():
    model = _real_model()
    entities = generate_cedar_entities(model, CATALOG_PATH)
    by_uid = {(e["uid"]["type"], e["uid"]["id"]): e for e in entities}
    mona = by_uid[("Agentic::Principal", "mona.commercial")]
    assert mona["parents"] == [{"type": "Agentic::Group", "id": "rfq-commercial-emea"}]


def test_no_business_resource_types_ever_generated():
    """Non-inference invariant (M3.5 acceptance criterion): only
    Principal/AgentPrincipal/Workload/Group, never RFQ/Quote/CarrierRate/etc."""
    model = _real_model()
    entities = generate_cedar_entities(model, CATALOG_PATH)
    allowed_types = {"Agentic::Principal", "Agentic::AgentPrincipal", "Agentic::Workload", "Agentic::Group"}
    seen_types = {e["uid"]["type"] for e in entities}
    assert seen_types <= allowed_types


def test_every_agent_entity_has_delegatable_actions_never_absent():
    """Artifact-boundary test (review round 2): the has-guard limitation
    documented in authorization/policies.cedar's forbid-delegation-outside-
    scope only stays inert if this holds -- every AgentPrincipal entity in
    the GENERATED output (not just generator source behavior) must have
    delegatable_actions present, as a list (possibly empty), never absent."""
    model = _real_model()
    entities = generate_cedar_entities(model, CATALOG_PATH)
    agents = [e for e in entities if e["uid"]["type"] == "Agentic::AgentPrincipal"]
    assert agents, "expected at least one AgentPrincipal entity"
    for a in agents:
        assert "delegatable_actions" in a["attrs"], a["uid"]
        assert isinstance(a["attrs"]["delegatable_actions"], list), a["uid"]


def test_catalog_id_mapping_mismatch_fails_loud(tmp_path):
    bad_catalog = tmp_path / "catalog.yaml"
    bad_catalog.write_text(
        yaml.safe_dump({"agents": [{"id": "not-a-standard-suffix", "caller_identity": {"can_call": []}}]}),
        encoding="utf-8",
    )
    model = _real_model()
    with pytest.raises(CedarEntityGenError):
        generate_cedar_entities(model, bad_catalog)
