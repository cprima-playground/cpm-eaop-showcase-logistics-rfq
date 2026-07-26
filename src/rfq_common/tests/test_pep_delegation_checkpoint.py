"""M4a second checkpoint: human initiator -> delegated agent -> MCP workload
-> PEP -> Cedar -> protected operation. One delegated operation
(route.recommend, via route-decision-agent/approval-mcp), proving permit,
deny, and the four specific properties requested -- not expanded across
every MCP server.

Naming correction (review round 3): this is an AGENT-TO-MCP operation
carrying claimed human-delegation context, NOT an A2A (agent-to-agent)
flow. No A2A protocol artifact is exercised here -- no agent discovery,
Agent Card, SendMessage/task lifecycle, A2A server endpoint, or one agent
invoking another agent rather than an MCP tool. `route-decision-agent`
authenticates directly to `approval-mcp` as an OAuth-credentialed MCP
client; Cedar's `AgentPrincipal` type says only what KIND of principal is
being authorized, not that the A2A protocol was used to reach this point.
`agents/catalog.yaml`'s `can_call` graph + the `agent.delegate` Cedar
action (M3.5) are Cedar-readiness for an eventual A2A authorization
boundary -- they are not, by themselves, evidence that A2A messages are
exchanged anywhere in this repo today. Accurate name for what this file
proves: "agent-to-MCP operation with claimed human delegation context."

Loads the REAL directory's Cedar entities (identity/actors.yaml +
agents/catalog.yaml, including the new delegatable_actions attribute) into
the isolated cedar-agent, same pattern as
test_pdp_integration.py::test_gen_cedar_entities_real_directory_can_call_edge.
MUST STAY LAST alphabetically-independent of that module (separate file,
own DataAdmin.put in its own fixture -- does not depend on or corrupt
test_pdp_integration.py's ad hoc fixture data, and itself doesn't need to
preserve state for anything after it).
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

RFQ_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RFQ_ROOT))

from rfq_common.pdp import DataAdmin, PolicyAdmin, PolicyBundle, SchemaAdmin, generate_schema
from rfq_common.pdp.entities import ref
from rfq_common.pep import AuthorizationDenied, ResolvedPrincipal, authorize_and_enforce

CEDAR_URL = "http://localhost:8280"


def _sidecar_up() -> bool:
    try:
        return httpx.get(f"{CEDAR_URL}/v1/policies", timeout=1.0).status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def pdp():
    if not _sidecar_up():
        pytest.skip(f"cedar-agent not running on {CEDAR_URL}")

    from tools.identity.gen_cedar_entities import generate_cedar_entities
    from tools.identity.validator import validate_identity

    import yaml
    projection = yaml.safe_load((RFQ_ROOT / "authorization" / "authz-projection.yaml").read_text(encoding="utf-8"))
    actions_doc = yaml.safe_load((RFQ_ROOT / "business" / "actions.yaml").read_text(encoding="utf-8"))
    schema = generate_schema(projection, actions_doc)
    bundle = PolicyBundle.from_path(RFQ_ROOT / "authorization" / "policies.cedar")

    model = validate_identity(
        RFQ_ROOT / "identity" / "actors.yaml",
        RFQ_ROOT / "identity" / "groups.yaml",
        RFQ_ROOT / "business" / "departments.yaml",
        RFQ_ROOT / "business" / "job-titles.yaml",
    )
    entities = generate_cedar_entities(model, RFQ_ROOT / "agents" / "catalog.yaml")

    PolicyAdmin(CEDAR_URL).put([])
    SchemaAdmin(CEDAR_URL).put(schema)
    PolicyAdmin(CEDAR_URL).put(bundle.policies())
    DataAdmin(CEDAR_URL).put(entities)
    return bundle


ROUTE_DECISION = ResolvedPrincipal(kind="agent", id="agent.route-decision", trust_domain="internal")
LANE_EVALUATION = ResolvedPrincipal(kind="agent", id="agent.lane-evaluation", trust_domain="internal")
COMMERCIAL_NORM = ResolvedPrincipal(kind="agent", id="agent.commercial-normalization", trust_domain="internal")

BASE_CONTEXT = {
    "cost_variance_pct_x10": 0,
    "transit_variance_days": 0,
    "margin_pct_x10": 70,
    "non_contracted_lane": False,
}


def test_property_1_and_2_human_stays_accountable_agent_stays_executing_principal(pdp):
    """Cedar's principal in the request is the AGENT (route-decision), never
    swapped for the human -- property #2. The human is recorded as the
    accountable delegator on AuthorizedContext, distinct from `principal`
    -- property #1."""
    ctx = authorize_and_enforce(
        CEDAR_URL, pdp, ROUTE_DECISION,
        action="route.recommend",
        resource=ref("RFQ", "RFQ-9001"),
        context={**BASE_CONTEXT, "delegated_by": "mona.commercial", "executing_workload": "workload.approval-mcp"},
        root=RFQ_ROOT,
    )
    assert ctx.decision.effect == "allow"
    # principal = executing agent, NOT the human -- never overwritten
    assert ctx.principal.kind == "agent"
    assert ctx.principal.id == "agent.route-decision"
    # human recorded separately, as the accountable delegator
    assert ctx.delegated_by == "mona.commercial"
    assert ctx.executing_workload == "workload.approval-mcp"


def test_property_5_audit_record_carries_both_identities(pdp):
    ctx = authorize_and_enforce(
        CEDAR_URL, pdp, ROUTE_DECISION,
        action="route.recommend",
        resource=ref("RFQ", "RFQ-9001"),
        context={**BASE_CONTEXT, "delegated_by": "mona.commercial", "executing_workload": "workload.approval-mcp"},
        root=RFQ_ROOT,
    )
    record = ctx.audit_record()
    assert record["principal_id"] == "agent.route-decision"          # executing
    assert record["claimed_delegator"] == "mona.commercial"           # CLAIMED, not verified -- see enforce.py
    assert record["executing_workload"] == "workload.approval-mcp"


def test_property_3_delegation_outside_agent_scope_denies(pdp):
    """lane-evaluation-agent's owned_actions (agents/catalog.yaml) do NOT
    include route.recommend -- a delegated attempt must deny, even though
    D3a would otherwise permit any active AgentPrincipal to recommend a
    contracted-lane route."""
    with pytest.raises(AuthorizationDenied) as exc:
        authorize_and_enforce(
            CEDAR_URL, pdp, LANE_EVALUATION,
            action="route.recommend",
            resource=ref("RFQ", "RFQ-9001"),
            context={**BASE_CONTEXT, "delegated_by": "mona.commercial"},
            root=RFQ_ROOT,
        )
    assert exc.value.decision.determining_policies == ["forbid-delegation-outside-scope"]


def test_non_delegated_call_unaffected_by_scope_rule(pdp):
    """Sanity: the SAME lane-evaluation-agent call, without delegated_by,
    is unaffected by the delegation-scope forbid -- proves the rule only
    fires when delegation is actually claimed, not as a general narrowing
    of route.recommend access."""
    ctx = authorize_and_enforce(
        CEDAR_URL, pdp, LANE_EVALUATION,
        action="route.recommend",
        resource=ref("RFQ", "RFQ-9001"),
        context=BASE_CONTEXT,
        root=RFQ_ROOT,
    )
    assert ctx.decision.effect == "allow"


def test_delegated_by_claim_carries_no_authorization_weight(pdp):
    """Review round 2, finding #1: `delegated_by` is a CLAIMED delegator,
    not a verified one -- authorize_and_enforce performs no resolution,
    signature check, or delegation-record lookup on it. Proven concretely:
    Cedar's decision is IDENTICAL whether delegated_by names a real,
    powerful, approval-authorized human (mona.commercial) or a completely
    fabricated one -- an untrusted request payload can self-assert
    anything here today, and it changes nothing about the authorization
    outcome (only the audit trail's claimed_delegator field). This is the
    gap ADR-003's future delegation-establishment path must close -- not
    closed here, made explicit here."""
    ctx_real = authorize_and_enforce(
        CEDAR_URL, pdp, ROUTE_DECISION,
        action="route.recommend",
        resource=ref("RFQ", "RFQ-9001"),
        context={**BASE_CONTEXT, "delegated_by": "mona.commercial"},
        root=RFQ_ROOT,
    )
    ctx_fake = authorize_and_enforce(
        CEDAR_URL, pdp, ROUTE_DECISION,
        action="route.recommend",
        resource=ref("RFQ", "RFQ-9001"),
        context={**BASE_CONTEXT, "delegated_by": "totally-fake-human-who-does-not-exist"},
        root=RFQ_ROOT,
    )
    assert ctx_real.decision.effect == ctx_fake.decision.effect == "allow"
    # only the audit trail differs -- authorization outcome does not
    assert ctx_real.delegated_by != ctx_fake.delegated_by

    # same story on the deny side: lane-evaluation is out of delegation
    # scope regardless of who (real or fake) is claimed as delegator
    with pytest.raises(AuthorizationDenied):
        authorize_and_enforce(
            CEDAR_URL, pdp, LANE_EVALUATION,
            action="route.recommend",
            resource=ref("RFQ", "RFQ-9001"),
            context={**BASE_CONTEXT, "delegated_by": "mona.commercial"},
            root=RFQ_ROOT,
        )
    with pytest.raises(AuthorizationDenied):
        authorize_and_enforce(
            CEDAR_URL, pdp, LANE_EVALUATION,
            action="route.recommend",
            resource=ref("RFQ", "RFQ-9001"),
            context={**BASE_CONTEXT, "delegated_by": "totally-fake-human-who-does-not-exist"},
            root=RFQ_ROOT,
        )


def test_property_4_delegation_cannot_grant_approval_authority(pdp):
    """A valid agent (executing under a workload, with delegated_by naming
    a human who DOES have approval authority) still cannot inherit that
    human's quote.approve permission -- quote.approve's principals type is
    [Principal] only (business/actions.yaml), a structural restriction no
    delegation context can route around. Proves 'a valid workload/agent
    identity with delegation context cannot inherit the human's
    permissions' -- the delegation context is inert for an action the
    agent's own principal TYPE can never hold, regardless of scope."""
    from rfq_common.pdp import PDPClient
    from rfq_common.pdp.entities import action_ref

    client = PDPClient(CEDAR_URL)
    decision = client.authorize(
        principal=ref("AgentPrincipal", "agent.commercial-normalization"),
        action=action_ref("quote.approve"),
        resource=ref("Quote", "Q-9001-v1"),
        context={"quote_value_eur_cents": 1000, "delegated_by": "mona.commercial"},
    )
    assert decision.effect == "deny"
