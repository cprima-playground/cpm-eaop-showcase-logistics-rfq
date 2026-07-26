"""Proves rfq_common.pdp genuinely reuses the RfQ authorization model -- loads the
REAL authorization/{authz-projection,actions,policies,obligations}.yaml, generates
a schema, bootstraps the already-running isolated cedar-agent (:8280, the same
instance the policy-evaluation spike uses), and verifies real decisions through
rfq_common's OWN PDPClient/PolicyBundle -- not the spike's ad hoc scripts.

Skips (not fails) if the isolated cedar-agent isn't up: `docker compose up -d` in
spikes/repricing/policy-evaluation/.
"""

import sys
from pathlib import Path

import httpx
import pytest
import yaml

from rfq_common.pdp import DataAdmin, PDPClient, PolicyAdmin, PolicyBundle, SchemaAdmin, action_ref, generate_schema, ref, uid

RFQ_ROOT = Path(__file__).resolve().parents[3]
CEDAR_URL = "http://localhost:8280"

sys.path.insert(0, str(RFQ_ROOT))  # tools/identity isn't an installed dependency of rfq_common


def _sidecar_up() -> bool:
    try:
        return httpx.get(f"{CEDAR_URL}/v1/policies", timeout=1.0).status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def pdp():
    if not _sidecar_up():
        pytest.skip(f"cedar-agent not running on {CEDAR_URL} (docker compose up -d in "
                     "spikes/repricing/policy-evaluation/)")

    projection = yaml.safe_load((RFQ_ROOT / "authorization" / "authz-projection.yaml").read_text(encoding="utf-8"))
    actions_doc = yaml.safe_load((RFQ_ROOT / "business" / "actions.yaml").read_text(encoding="utf-8"))
    schema = generate_schema(projection, actions_doc)
    bundle = PolicyBundle.from_path(RFQ_ROOT / "authorization" / "policies.cedar")

    PolicyAdmin(CEDAR_URL).put([])  # clear
    SchemaAdmin(CEDAR_URL).put(schema)
    PolicyAdmin(CEDAR_URL).put(bundle.policies())
    DataAdmin(CEDAR_URL).put([
        {"uid": uid("AgentPrincipal", "commercial-normalization-agent"),
         "attrs": {"kind": "agent", "active": True, "trust_domain": "internal",
                    "canonical_id": "agent.commercial-normalization"}, "parents": []},
        {"uid": uid("Principal", "mona.commercial"),
         "attrs": {"kind": "human", "active": True}, "parents": [uid("Group", "rfq-commercial-emea")]},
        {"uid": uid("Group", "rfq-commercial-emea"), "attrs": {}, "parents": []},
        {"uid": uid("Workload", "workload.tms-mcp"),
         "attrs": {"kind": "workload", "active": True, "system": "tms", "trust_domain": "internal"}, "parents": []},
        {"uid": uid("Workload", "workload.external-mcp"),
         "attrs": {"kind": "workload", "active": True, "system": "external", "trust_domain": "external"}, "parents": []},
        {"uid": uid("AgentPrincipal", "agent.lane-evaluation"),
         "attrs": {"kind": "agent", "active": True, "trust_domain": "internal",
                    "canonical_id": "agent.lane-evaluation",
                    "can_call": ["agent.commercial-normalization"]}, "parents": []},
    ])
    return bundle


def test_schema_generation_matches_committed_schema(pdp):
    """rfq_common.pdp.generate_schema on the real files produces the same schema
    already committed at authorization/agentic.cedarschema (proves it's genuinely
    the generator, not a divergent reimplementation)."""
    import json

    projection = yaml.safe_load((RFQ_ROOT / "authorization" / "authz-projection.yaml").read_text(encoding="utf-8"))
    actions_doc = yaml.safe_load((RFQ_ROOT / "business" / "actions.yaml").read_text(encoding="utf-8"))
    regenerated = generate_schema(projection, actions_doc)
    committed = json.loads((RFQ_ROOT / "authorization" / "agentic.cedarschema").read_text(encoding="utf-8"))
    assert regenerated == committed


def test_fresh_fx_read_allowed_via_rfq_common_pdp_client(pdp):
    """Scenario 01 step 1, driven end-to-end through rfq_common's own PDPClient."""
    client = PDPClient(CEDAR_URL)
    decision = client.authorize(
        principal=ref("AgentPrincipal", "commercial-normalization-agent"),
        action=action_ref("fx-rate.read"),
        resource=ref("ExchangeRate", "CNY-EUR"),
        context={"fx_age_seconds": 720, "quote_currency": "EUR"},
    )
    assert decision.effect == "allow"
    assert decision.determining_policies == ["commercial-may-read-fresh-fx"]


def test_forbid_beats_permit_via_rfq_common_pdp_client(pdp):
    """Scenario 01's D4b: FX moved > 2% -> forbid wins (deny-precedence)."""
    client = PDPClient(CEDAR_URL)
    decision = client.authorize(
        principal=ref("AgentPrincipal", "commercial-normalization-agent"),
        action=action_ref("quote.submit-for-approval"),
        resource=ref("Quote", "Q-1001-v2"),
        context={"fx_variance_pct_x10": 27, "margin_pct_x10": 50},
    )
    assert decision.effect == "deny"
    assert decision.determining_policies == ["forbid-auto-replace-on-fx"]


def test_obligation_resolution_via_policy_bundle(pdp):
    """D3b+D8 obligations merge, resolved via rfq_common's PolicyBundle -- same
    logic the spike's bundle.py has, now a reusable library function."""
    client = PDPClient(CEDAR_URL)
    decision = client.authorize(
        principal=ref("AgentPrincipal", "commercial-normalization-agent"),
        action=action_ref("route.recommend"),
        resource=ref("RFQ", "RFQ-1001"),
        context={"non_contracted_lane": True, "cost_variance_pct_x10": 93, "margin_pct_x10": 50},
    )
    assert decision.effect == "allow"
    obligations = pdp.resolve_obligation_ids(decision.determining_policies)
    assert sorted(obligations) == sorted(["oblig-cost-variance-review", "oblig-lane-deviation"])


def test_agent_may_connect_to_workload_in_same_trust_domain(pdp):
    """ADR-001: mcp.connect permits an agent to open a session with a workload
    sharing its trust_domain (both 'internal' here)."""
    client = PDPClient(CEDAR_URL)
    decision = client.authorize(
        principal=ref("AgentPrincipal", "commercial-normalization-agent"),
        action=action_ref("mcp.connect"),
        resource=ref("Workload", "workload.tms-mcp"),
        context={},
    )
    assert decision.effect == "allow"
    assert decision.determining_policies == ["agent-may-connect-same-trust-domain"]


def test_agent_denied_connect_to_workload_in_different_trust_domain(pdp):
    """ADR-001: mcp.connect denies when trust_domain differs (agent is
    'internal', workload.external-mcp is 'external') -- no permit matches,
    default-deny."""
    client = PDPClient(CEDAR_URL)
    decision = client.authorize(
        principal=ref("AgentPrincipal", "commercial-normalization-agent"),
        action=action_ref("mcp.connect"),
        resource=ref("Workload", "workload.external-mcp"),
        context={},
    )
    assert decision.effect == "deny"


def test_agent_may_delegate_to_can_call_entry(pdp):
    """M3.5: agent.delegate permits lane-evaluation -> commercial-
    normalization, matching agents/catalog.yaml's can_call edge."""
    client = PDPClient(CEDAR_URL)
    decision = client.authorize(
        principal=ref("AgentPrincipal", "agent.lane-evaluation"),
        action=action_ref("agent.delegate"),
        resource=ref("AgentPrincipal", "commercial-normalization-agent"),
        context={},
    )
    assert decision.effect == "allow"
    assert decision.determining_policies == ["agent-may-delegate-per-catalog"]


def test_agent_denied_delegate_to_non_can_call_entry(pdp):
    """No can_call edge from lane-evaluation to itself -- default deny."""
    client = PDPClient(CEDAR_URL)
    decision = client.authorize(
        principal=ref("AgentPrincipal", "agent.lane-evaluation"),
        action=action_ref("agent.delegate"),
        resource=ref("AgentPrincipal", "agent.lane-evaluation"),
        context={},
    )
    assert decision.effect == "deny"


def test_manager_may_approve_quote_within_limit(pdp):
    """D19 (Finding 3, capability-profile review): quote.approve, distinct
    from D6's route-deviation.approve -- resource is Quote, not
    RouteRecommendation, matching mock_qms's real decision endpoint."""
    client = PDPClient(CEDAR_URL)
    decision = client.authorize(
        principal=ref("Principal", "mona.commercial"),
        action=action_ref("quote.approve"),
        resource=ref("Quote", "Q-1001-v2"),
        context={"quote_value_eur_cents": 645263},
    )
    assert decision.effect == "allow"
    assert decision.determining_policies == ["commercial-manager-may-approve-quote"]


def test_manager_may_reject_quote_no_value_limit(pdp):
    """D20: reject has no value-limit gate -- declining doesn't commit the
    company to anything, unlike approving."""
    client = PDPClient(CEDAR_URL)
    decision = client.authorize(
        principal=ref("Principal", "mona.commercial"),
        action=action_ref("quote.reject"),
        resource=ref("Quote", "Q-1001-v2"),
        context={},
    )
    assert decision.effect == "allow"
    assert decision.determining_policies == ["commercial-manager-may-reject-quote"]


def test_manager_may_request_quote_revision(pdp):
    """D21: matches mock_qms's third real decision outcome."""
    client = PDPClient(CEDAR_URL)
    decision = client.authorize(
        principal=ref("Principal", "mona.commercial"),
        action=action_ref("quote.request-revision"),
        resource=ref("Quote", "Q-1001-v2"),
        context={},
    )
    assert decision.effect == "allow"
    assert decision.determining_policies == ["commercial-manager-may-request-quote-revision"]


def test_agent_cannot_approve_quote(pdp):
    """quote.approve's schema-level appliesTo.principalTypes is [Principal]
    only (business/actions.yaml) -- an AgentPrincipal can't even construct a
    valid request for it. Confirms the structural guarantee, not just the
    policy-level one."""
    client = PDPClient(CEDAR_URL)
    decision = client.authorize(
        principal=ref("AgentPrincipal", "commercial-normalization-agent"),
        action=action_ref("quote.approve"),
        resource=ref("Quote", "Q-1001-v2"),
        context={"quote_value_eur_cents": 645263},
    )
    assert decision.effect == "deny"


def test_manager_approval_within_limit(pdp):
    """D6: group membership + context threshold, via rfq_common."""
    client = PDPClient(CEDAR_URL)
    decision = client.authorize(
        principal=ref("Principal", "mona.commercial"),
        action=action_ref("route-deviation.approve"),
        resource=ref("RouteRecommendation", "REC-1001-v2"),
        context={"quote_value_eur_cents": 645263, "fx_variance_pct_x10": 27, "margin_pct_x10": 50},
    )
    assert decision.effect == "allow"
    assert decision.determining_policies == ["manager-may-approve-within-limit"]


def test_gen_cedar_entities_real_directory_can_call_edge(pdp):
    """M3.5 verification bullet, done for real: load the ACTUAL identity/
    actors.yaml + agents/catalog.yaml directory (not ad hoc fixture data)
    through tools.identity.gen_cedar_entities, and confirm a real can_call
    edge resolves allow via rfq_common's own PDPClient.

    MUST STAY LAST in this file: DataAdmin.put() replaces the cedar-agent's
    entity data wholesale, overwriting the ad hoc fixture data every other
    test in this module depends on.
    """
    from tools.identity.gen_cedar_entities import generate_cedar_entities
    from tools.identity.validator import validate_identity

    model = validate_identity(
        RFQ_ROOT / "identity" / "actors.yaml",
        RFQ_ROOT / "identity" / "groups.yaml",
        RFQ_ROOT / "business" / "departments.yaml",
        RFQ_ROOT / "business" / "job-titles.yaml",
    )
    entities = generate_cedar_entities(model, RFQ_ROOT / "agents" / "catalog.yaml")
    DataAdmin(CEDAR_URL).put(entities)

    client = PDPClient(CEDAR_URL)

    allowed = client.authorize(
        principal=ref("AgentPrincipal", "agent.lane-evaluation"),
        action=action_ref("agent.delegate"),
        resource=ref("AgentPrincipal", "agent.commercial-normalization"),
        context={},
    )
    assert allowed.effect == "allow"
    assert allowed.determining_policies == ["agent-may-delegate-per-catalog"]

    denied = client.authorize(
        principal=ref("AgentPrincipal", "agent.commercial-normalization"),
        action=action_ref("agent.delegate"),
        resource=ref("AgentPrincipal", "agent.lane-evaluation"),
        context={},
    )
    assert denied.effect == "deny"
