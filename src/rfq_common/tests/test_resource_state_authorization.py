"""M6 (qms-mcp): rfq_common.pep.authorize_and_enforce's `additional_entities`
plumbing -- request-scoped resource facts (rfq_common.pdp.entities.entity())
supplied ONLY for one is_authorized call, verified against cedar-agent's
real `/v1/is_authorized` (its OpenAPI schema documents `additional_entities`
directly; confirmed empirically before wiring this in). Never touches the
persisted entity store (DataAdmin.put()) -- that stays reachable only from
seed/admin code, never request-handling code, per rfq_common.pdp.admin's
own module docstring.

Proven against two REAL business policies (authorization/policies.cedar),
not a throwaway test-only policy: agent-may-calculate-quote-price-when-draft
and agent-may-evaluate-quote-variance-when-priced -- the first genuinely
resource/state-sensitive MCP-mediated decisions in this repo (M6's own
design goal: not another D10/D11-style blanket "active internal agent"
check).

Skips (not fails) if the isolated cedar-agent isn't up.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import yaml

from rfq_common.pdp import DataAdmin, PolicyAdmin, PolicyBundle, SchemaAdmin, generate_schema
from rfq_common.pdp.entities import entity, ref
from rfq_common.pep import AuthorizationDenied, ResolvedPrincipal, authorize_and_enforce

RFQ_ROOT = Path(__file__).resolve().parents[3]
CEDAR_URL = "http://localhost:8280"


def _cedar_up() -> bool:
    try:
        return httpx.get(f"{CEDAR_URL}/v1/policies", timeout=1.0).status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def pdp():
    if not _cedar_up():
        pytest.skip(f"cedar-agent not running on {CEDAR_URL}")

    import sys
    sys.path.insert(0, str(RFQ_ROOT))
    from tools.identity.gen_cedar_entities import generate_cedar_entities
    from tools.identity.validator import validate_identity

    projection = yaml.safe_load((RFQ_ROOT / "authorization" / "authz-projection.yaml").read_text(encoding="utf-8"))
    actions_doc = yaml.safe_load((RFQ_ROOT / "business" / "actions.yaml").read_text(encoding="utf-8"))
    schema = generate_schema(projection, actions_doc)
    bundle = PolicyBundle.from_path(RFQ_ROOT / "authorization" / "policies.cedar")

    model = validate_identity(
        RFQ_ROOT / "identity" / "actors.yaml", RFQ_ROOT / "identity" / "groups.yaml",
        RFQ_ROOT / "business" / "departments.yaml", RFQ_ROOT / "business" / "job-titles.yaml",
    )
    entities = generate_cedar_entities(model, RFQ_ROOT / "agents" / "catalog.yaml")

    PolicyAdmin(CEDAR_URL).put([])
    SchemaAdmin(CEDAR_URL).put(schema)
    PolicyAdmin(CEDAR_URL).put(bundle.policies())
    DataAdmin(CEDAR_URL).put(entities)
    return bundle


COMMERCIAL_NORM = ResolvedPrincipal(kind="agent", id="agent.commercial-normalization", trust_domain="internal")


def test_quote_price_calculate_permits_when_resource_status_is_draft_live(pdp):
    """resource.status supplied ONLY via additional_entities -- never
    pre-loaded into the persisted store (no DataAdmin.put() for this
    Quote anywhere in this test)."""
    ctx = authorize_and_enforce(
        CEDAR_URL, pdp, COMMERCIAL_NORM,
        action="quote-price.calculate",
        resource=ref("Quote", "Q-TEST-1"),
        context={},
        root=RFQ_ROOT,
        additional_entities=[entity("Quote", "Q-TEST-1", {"status": "draft"})],
    )
    assert ctx.decision.effect == "allow"


def test_quote_price_calculate_denies_when_resource_status_is_priced_live(pdp):
    """SAME quote id, SAME policy, only the live status fact differs --
    proves the decision tracks the resource's real current state, not a
    cached/stale copy."""
    with pytest.raises(AuthorizationDenied):
        authorize_and_enforce(
            CEDAR_URL, pdp, COMMERCIAL_NORM,
            action="quote-price.calculate",
            resource=ref("Quote", "Q-TEST-1"),
            context={},
            root=RFQ_ROOT,
            additional_entities=[entity("Quote", "Q-TEST-1", {"status": "priced"})],
        )


def test_quote_variance_evaluate_denies_on_draft_permits_once_priced(pdp):
    """The inverse gate: variance evaluation requires a PRICED snapshot to
    exist -- denied on draft, permitted once priced. Same quote id, two
    calls, only the live fact changes."""
    with pytest.raises(AuthorizationDenied):
        authorize_and_enforce(
            CEDAR_URL, pdp, COMMERCIAL_NORM,
            action="quote-variance.evaluate",
            resource=ref("Quote", "Q-TEST-2"),
            context={},
            root=RFQ_ROOT,
            additional_entities=[entity("Quote", "Q-TEST-2", {"status": "draft"})],
        )

    ctx = authorize_and_enforce(
        CEDAR_URL, pdp, COMMERCIAL_NORM,
        action="quote-variance.evaluate",
        resource=ref("Quote", "Q-TEST-2"),
        context={},
        root=RFQ_ROOT,
        additional_entities=[entity("Quote", "Q-TEST-2", {"status": "priced"})],
    )
    assert ctx.decision.effect == "allow"


def test_additional_entities_never_touches_the_persisted_store(pdp):
    """After all the calls above (each with its own additional_entities),
    a call WITHOUT additional_entities for the same resource must NOT see
    a status at all -- proving nothing leaked into cedar-agent's
    persisted entity store."""
    with pytest.raises(AuthorizationDenied) as exc:
        authorize_and_enforce(
            CEDAR_URL, pdp, COMMERCIAL_NORM,
            action="quote-price.calculate",
            resource=ref("Quote", "Q-TEST-1"),
            context={},
            root=RFQ_ROOT,
        )
    assert exc.value.decision.determining_policies == []
