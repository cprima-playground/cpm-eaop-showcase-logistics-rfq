"""Middle-hop deny: commercial-normalization-agent's real can_call edge
(agents/catalog.yaml: [route-decision-agent]) must NOT be removed or
mutated to manufacture a deny -- same instruction as
route-decision-agent/tests/test_second_hop_deny.py. Instead, this proves
the SAME enforcement primitive CommercialNormalizationExecutor calls
(rfq_common.pep.authorize_and_enforce, action=agent.delegate) genuinely
denies for a real non-edge, exercised directly against the real,
live-generated Cedar entities.

agent.commercial-normalization's real can_call is [agent.route-decision]
only -- agent.lane-evaluation is NOT one of its callees (lane-evaluation
is what CALLS commercial-normalization, not the reverse), so
commercial-normalization-agent attempting to delegate to
lane-evaluation-agent is a genuine, unmodified non-edge.
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


COMMERCIAL_NORM = ResolvedPrincipal(kind="agent", id="agent.commercial-normalization", trust_domain="internal")


def test_commercial_normalization_real_can_call_is_route_decision_only():
    """Documents today's actual edge -- update deliberately if a second
    edge is ever added."""
    import yaml
    catalog = yaml.safe_load((RFQ_ROOT / "agents" / "catalog.yaml").read_text(encoding="utf-8"))
    commercial = next(a for a in catalog["agents"] if a["id"] == "commercial-normalization-agent")
    assert commercial["caller_identity"]["can_call"] == ["route-decision-agent"]


def test_middle_hop_child_call_denied_for_a_real_non_edge(pdp):
    """commercial-normalization-agent attempting agent.delegate against
    agent.lane-evaluation -- NOT in its can_call -- must deny, via the
    exact same rfq_common.pep.authorize_and_enforce call
    CommercialNormalizationExecutor makes for its real
    route-decision-agent target."""
    with pytest.raises(AuthorizationDenied) as exc:
        authorize_and_enforce(
            CEDAR_URL, pdp, COMMERCIAL_NORM,
            action="agent.delegate",
            resource=ref("AgentPrincipal", "agent.lane-evaluation"),
            context={"skill": "some-hypothetical-skill"},
            root=RFQ_ROOT,
        )
    assert exc.value.decision.determining_policies == []


def test_middle_hop_real_edge_still_permits(pdp):
    """Sanity: the REAL edge (route-decision-agent) is unaffected."""
    ctx = authorize_and_enforce(
        CEDAR_URL, pdp, COMMERCIAL_NORM,
        action="agent.delegate",
        resource=ref("AgentPrincipal", "agent.route-decision"),
        context={"skill": "recommend-route"},
        root=RFQ_ROOT,
    )
    assert ctx.decision.effect == "allow"
