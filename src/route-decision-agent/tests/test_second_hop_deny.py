"""Second-hop deny: route-decision-agent's real can_call edge
(agents/catalog.yaml: [lane-evaluation-agent]) must NOT be removed or
mutated to manufacture a deny -- that would test a fictional deployment,
not the real one (per explicit instruction). Instead, this proves the
SAME enforcement primitive route_decision_agent.executor.RouteRecommend
ationExecutor calls (rfq_common.pep.authorize_and_enforce, action=
agent.delegate) genuinely denies for a non-edge -- exercised directly
against the real, live-generated Cedar entities, same pattern
test_pdp_integration.py's own can_call edge/non-edge checks already use.

agent.route-decision's real can_call is [agent.lane-evaluation] only
(agents/catalog.yaml) -- agent.commercial-normalization is NOT one of its
callees, so route-decision-agent attempting to delegate to
commercial-normalization-agent is a genuine, unmodified non-edge.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

RFQ_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RFQ_ROOT))

from rfq_common.pdp import DataAdmin, PolicyAdmin, PolicyBundle, SchemaAdmin, generate_schema  # noqa: E402
from rfq_common.pdp.entities import ref  # noqa: E402
from rfq_common.pep import AuthorizationDenied, ResolvedPrincipal, authorize_and_enforce  # noqa: E402

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

    import yaml
    from tools.identity.gen_cedar_entities import generate_cedar_entities
    from tools.identity.validator import validate_identity

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


def test_route_decision_real_can_call_is_lane_evaluation_only():
    """Documents today's actual edge (not a permanent limit -- update this,
    deliberately, when a second edge is added)."""
    import yaml
    catalog = yaml.safe_load((RFQ_ROOT / "agents" / "catalog.yaml").read_text(encoding="utf-8"))
    route_decision = next(a for a in catalog["agents"] if a["id"] == "route-decision-agent")
    assert route_decision["caller_identity"]["can_call"] == ["lane-evaluation-agent"]


def test_second_hop_child_call_denied_for_a_real_non_edge(pdp):
    """route-decision-agent attempting agent.delegate against
    agent.commercial-normalization -- NOT in its can_call -- must deny,
    via the exact same rfq_common.pep.authorize_and_enforce call
    RouteRecommendationExecutor makes for its real lane-evaluation-agent
    target. Proves the enforcement primitive is correct generically, not
    that route-decision-agent's live executor was pointed somewhere it
    isn't in production."""
    with pytest.raises(AuthorizationDenied) as exc:
        authorize_and_enforce(
            CEDAR_URL, pdp, ROUTE_DECISION,
            action="agent.delegate",
            resource=ref("AgentPrincipal", "agent.commercial-normalization"),
            context={"skill": "some-hypothetical-skill"},
            root=RFQ_ROOT,
        )
    assert exc.value.decision.determining_policies == []


def test_second_hop_real_edge_still_permits(pdp):
    """Sanity: the REAL edge (lane-evaluation-agent) is unaffected --
    proves the deny above is about the specific non-edge, not a broken
    policy that denies everything."""
    ctx = authorize_and_enforce(
        CEDAR_URL, pdp, ROUTE_DECISION,
        action="agent.delegate",
        resource=ref("AgentPrincipal", "agent.lane-evaluation"),
        context={"skill": "evaluate-lane-capacity"},
        root=RFQ_ROOT,
    )
    assert ctx.decision.effect == "allow"
