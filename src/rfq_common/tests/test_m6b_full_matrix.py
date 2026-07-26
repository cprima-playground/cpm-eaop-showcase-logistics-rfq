"""M6b: full A2A x MCP matrix, per agents/catalog.yaml's can_call/mcp_access.

Library-level (rfq_common.pep.authorize + real cedar-agent, real seeded
directory entities) -- no A2A/HTTP/Keycloak-token layer needed, since
Cedar's decision depends only on the resolved principal id/kind + the
loaded entity attributes, not on how that principal was authenticated.
Mirrors the ResolvedPrincipal shape every real caller resolves to, built
directly here instead of round-tripping through a real token.

Two real, load-bearing findings this matrix makes concrete rather than
theoretical (same posture as M6a's D10 discovery -- "originally-planned
ownership-based deny test turned out to be a real allow"). NEITHER is
fixed here: tightening Cedar policy is new business/policy content
(CLAUDE.md's structure-vs-policy split) that needs explicit authorization,
not something a matrix test should silently invent.

1. `agents/catalog.yaml`'s `mcp_access`/`owned_actions` are DESCRIPTIVE
   ONLY -- not Cedar-enforced. Every real tool-action policy
   (capacity.check, carrier-rate.read, quote-price.calculate,
   quote-variance.evaluate, route-deviation.propose) gates only on
   `active` + `trust_domain == "internal"` (+ live resource state where
   relevant, e.g. a Quote's status) -- never on which agent "owns" the
   action. Any active internal agent is Cedar-permitted to call any of
   these actions, regardless of agents/catalog.yaml's declared ownership.

2. `route.recommend` (D3a/D3b/D8/D9) and `route-cost.normalize` (D2) have
   NO trust_domain condition at all -- only context flags (+
   `principal.active` for route.recommend). Even `agent.trust-boundary-
   fixture` (the M6a fixture whose entire declared purpose is to sit
   OUTSIDE the internal trust domain) is Cedar-permitted to call them.
   `mcp.connect` (ADR-001's transport-level check) is the only thing that
   actually stops an external-trust-domain agent from reaching an
   internal-trust-domain MCP workload at all -- these two actions have no
   equivalent gate of their own.

Only `agent.delegate` (can_call) and the human-approval actions (Cedar
group membership) are genuinely agent/group-specific today.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from rfq_common.pdp import DataAdmin, PolicyAdmin, PolicyBundle, SchemaAdmin, generate_schema
from rfq_common.pdp.entities import entity, ref
from rfq_common.pep.enforce import authorize
from rfq_common.pep.resolve import ResolvedPrincipal
from tools.identity.gen_cedar_entities import generate_cedar_entities
from tools.identity.validator import validate_identity

RFQ_ROOT = Path(__file__).resolve().parents[3]
CEDAR_URL = "http://localhost:8280"

AGENT_IDS = [
    "agent.lane-evaluation",
    "agent.commercial-normalization",
    "agent.route-decision",
    "agent.trust-boundary-fixture",
]
WORKLOAD_IDS = ["workload.tms-mcp", "workload.rate-mcp", "workload.qms-mcp", "workload.approval-mcp"]


def _cedar_up() -> bool:
    import httpx
    try:
        return httpx.get(f"{CEDAR_URL}/v1/policies", timeout=1.0).status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def preconditions():
    if not _cedar_up():
        pytest.skip("cedar-agent (:8280) not running")


@pytest.fixture(scope="module")
def real_directory_entities_loaded(preconditions):
    """Same pattern as every other checkpoint suite's fixture of this
    name (tms-mcp/route-decision-agent/commercial-normalization-agent) --
    duplicated rather than imported cross-package, matching this repo's
    existing convention of not creating test-only cross-package deps."""
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


def _catalog() -> dict:
    return yaml.safe_load((RFQ_ROOT / "agents" / "catalog.yaml").read_text(encoding="utf-8"))


def _can_call_by_id() -> dict[str, list[str]]:
    doc = _catalog()
    out = {}
    for agent in doc["agents"]:
        canonical = "agent." + agent["id"].removesuffix("-agent")
        out[canonical] = ["agent." + c.removesuffix("-agent") for c in agent["caller_identity"].get("can_call", [])]
    return out


def _trust_domain_by_id() -> dict[str, str]:
    doc = yaml.safe_load((RFQ_ROOT / "identity" / "actors.yaml").read_text(encoding="utf-8"))
    out = {}
    for actor in doc.get("actors", doc.get("principals", [])):
        if actor.get("kind") in ("agent", "workload") and "trust_domain" in actor:
            out[actor["id"]] = actor["trust_domain"]
    return out


def _principal(canonical_id: str) -> ResolvedPrincipal:
    kind = "agent" if canonical_id.startswith("agent.") else "workload"
    return ResolvedPrincipal(kind=kind, id=canonical_id, provider="keycloak")


def _permit(action: str, principal_id: str, resource: str, *, context: dict | None = None,
            additional_entities: list[dict] | None = None) -> bool:
    decision = authorize(CEDAR_URL, _principal(principal_id), action, resource,
                          context or {}, additional_entities=additional_entities)
    return decision.effect == "allow"


# ---------------------------------------------------------------- agent.delegate

def test_agent_delegate_matrix_matches_can_call_exactly(real_directory_entities_loaded):
    can_call = _can_call_by_id()
    results = {}
    for caller in AGENT_IDS:
        for callee in AGENT_IDS:
            if caller == callee:
                continue
            results[(caller, callee)] = _permit(
                "agent.delegate", caller, ref("AgentPrincipal", callee),
            )
    for (caller, callee), permitted in results.items():
        expected = callee in can_call.get(caller, [])
        assert permitted == expected, f"{caller} -> {callee}: expected permit={expected}, got {permitted}"


# -------------------------------------------------------------------- mcp.connect

def test_mcp_connect_matrix_is_trust_domain_only_not_mcp_access(real_directory_entities_loaded):
    """Documents the real behavior precisely: mcp.connect permits iff
    trust_domain matches -- NOT restricted to the specific workloads an
    agent's mcp_access list names. E.g. lane-evaluation-agent's mcp_access
    is [tms-mcp, rate-mcp] only, but this asserts it ALSO gets a real
    Cedar permit to connect to qms-mcp/approval-mcp (same trust domain) --
    the transport-level check is broader than the catalog's stated
    per-agent scope."""
    trust_domain = _trust_domain_by_id()
    results = {}
    for agent_id in AGENT_IDS:
        for workload_id in WORKLOAD_IDS:
            results[(agent_id, workload_id)] = _permit(
                "mcp.connect", agent_id, ref("Workload", workload_id),
            )
    for (agent_id, workload_id), permitted in results.items():
        expected = trust_domain.get(agent_id) == trust_domain.get(workload_id)
        assert permitted == expected, f"{agent_id} -> {workload_id}: expected permit={expected}, got {permitted}"

    # The concrete gap: lane-evaluation-agent's mcp_access is [tms-mcp,
    # rate-mcp] only, yet it's permitted to connect to qms-mcp too.
    assert results[("agent.lane-evaluation", "workload.qms-mcp")] is True


# --------------------------------------------------- tool actions: ownership gap

def test_owned_actions_are_not_cedar_enforced_for_capacity_and_rate(real_directory_entities_loaded):
    """route-decision-agent does NOT own capacity.check or carrier-rate.read
    (agents/catalog.yaml: its owned_actions is [route.recommend,
    route-deviation.propose]) -- yet D10/agent-may-read-carrier-rate permit
    any active internal agent, so it gets a real Cedar permit anyway."""
    assert _permit("capacity.check", "agent.route-decision", ref("RouteOption", "SHA-HAM-MUC")) is True
    assert _permit("carrier-rate.read", "agent.route-decision", ref("RouteOption", "SHA-HAM-MUC")) is True

    # trust_domain is the only real gate on these two actions: the external
    # fixture agent is denied, same real D10 condition M6a already proved.
    assert _permit("capacity.check", "agent.trust-boundary-fixture", ref("RouteOption", "SHA-HAM-MUC")) is False
    assert _permit("carrier-rate.read", "agent.trust-boundary-fixture", ref("RouteOption", "SHA-HAM-MUC")) is False


def test_owned_actions_are_not_cedar_enforced_for_quote_state_actions(real_directory_entities_loaded):
    """lane-evaluation-agent does NOT own quote-price.calculate (that's
    commercial-normalization-agent's), yet the policy only checks
    trust_domain + the live resource state supplied via additional_entities
    -- it gets a real permit here too, same gap, different action family."""
    draft_quote = [entity("Quote", "Q-TEST-001", {"status": "draft"})]
    assert _permit(
        "quote-price.calculate", "agent.lane-evaluation", ref("Quote", "Q-TEST-001"),
        additional_entities=draft_quote,
    ) is True


def test_route_recommend_and_route_cost_normalize_have_no_trust_domain_gate(real_directory_entities_loaded):
    """The most surprising finding: unlike capacity.check/carrier-rate.read/
    the quote-state actions, route.recommend (D3a) and route-cost.normalize
    (D2) check NO principal attribute beyond `active` (route.recommend) or
    nothing at all (route-cost.normalize) -- the external-trust-domain
    fixture agent, which D10 correctly denies for capacity.check, gets a
    real Cedar PERMIT for both of these."""
    assert _permit(
        "route.recommend", "agent.trust-boundary-fixture", ref("RFQ", "RFQ-TEST-001"),
        context={"non_contracted_lane": False},
    ) is True
    assert _permit(
        "route-cost.normalize", "agent.trust-boundary-fixture", ref("RouteOption", "SHA-HAM-MUC"),
        context={"fx_age_seconds": 60},
    ) is True
