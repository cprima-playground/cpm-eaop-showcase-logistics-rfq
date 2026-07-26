"""M5 (remaining scope) / SDK-level protocol integration for the full
4-hop chain:

  lane-evaluation-agent -A2A-> commercial-normalization-agent
      -A2A-> route-decision-agent -A2A-> lane-evaluation-agent
      -MCP-> tms-mcp -> mock-tms

Each hop authenticates and authorizes its IMMEDIATE caller only, same
discipline as M5b's 3-hop chain. This is the SDK-level/in-process
counterpart (all 4 apps mounted via httpx.ASGITransport) -- see
test_network_checkpoint.py for the real-process, real-socket version
(this milestone's actual "Checkpoint 4", per direct instruction that a
network-only claim must be proven at the network level, not just here).

No layer's code is mocked. Real Keycloak tokens + introspection, real
cedar-agent, real mock-tms (already-running live process, :8004).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
import pytest

RFQ_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RFQ_ROOT / "src" / "mock-tms"))
sys.path.insert(0, str(RFQ_ROOT / "src" / "tms-mcp"))
sys.path.insert(0, str(RFQ_ROOT / "src" / "lane-evaluation-agent"))
sys.path.insert(0, str(RFQ_ROOT / "src" / "route-decision-agent"))
sys.path.insert(0, str(RFQ_ROOT))

from a2a.client import A2ACardResolver, ClientConfig, create_client  # noqa: E402
from a2a.client.client import ClientCallContext  # noqa: E402
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState  # noqa: E402

from commercial_normalization_agent.api import build_app as build_commercial_app  # noqa: E402
from commercial_normalization_agent.executor import SKILL_ID as COMMERCIAL_SKILL_ID  # noqa: E402
from lane_evaluation_agent.api import build_app as build_lane_app  # noqa: E402
from route_decision_agent.api import build_app as build_route_app  # noqa: E402
from tms_mcp.api import build_app as build_tms_mcp_app  # noqa: E402

KEYCLOAK_URL = "http://localhost:8081"
CEDAR_URL = "http://localhost:8280"
TMS_URL = "http://127.0.0.1:8004"
ROUTE_ID = "SHA-HAM-MUC"
UNKNOWN_ROUTE_ID = "NONEXISTENT-ROUTE-XYZ"


def _keycloak_up() -> bool:
    try:
        return httpx.get(f"{KEYCLOAK_URL}/realms/rfq", timeout=1.0).status_code == 200
    except Exception:
        return False


def _cedar_up() -> bool:
    try:
        return httpx.get(f"{CEDAR_URL}/v1/policies", timeout=1.0).status_code == 200
    except Exception:
        return False


def _tms_up() -> bool:
    try:
        return httpx.get(f"{TMS_URL}/healthz", timeout=1.0).status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def preconditions():
    if not (_keycloak_up() and _cedar_up() and _tms_up()):
        pytest.skip("Keycloak (:8081), cedar-agent (:8280), or mock-tms (:8004) not running")


@pytest.fixture(scope="module")
def real_directory_entities_loaded(preconditions):
    """cedar-agent is a shared sidecar; seed the real directory explicitly
    -- same rationale as every other real-stack checkpoint file."""
    import yaml
    from rfq_common.pdp import DataAdmin, PolicyAdmin, PolicyBundle, SchemaAdmin, generate_schema
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


async def _client_credentials_token(client_id: str, client_secret: str) -> str | None:
    if not client_secret:
        return None
    async with httpx.AsyncClient() as c:
        r = await c.post(
            f"{KEYCLOAK_URL}/realms/rfq/protocol/openid-connect/token",
            data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
        )
    if r.status_code != 200:
        return None
    return r.json()["access_token"]


@pytest.fixture()
async def lane_eval_token_as_root_caller(preconditions):
    """lane-evaluation-agent's own token, used here as the REAL A2A caller
    of commercial-normalization-agent -- lane-evaluation-agent.can_call
    includes commercial-normalization-agent (agents/catalog.yaml), a real,
    unmodified edge, and the entry point into the full chain."""
    token = await _client_credentials_token(
        "lane-evaluation-agent-svc", os.environ.get("LANE_EVAL_AGENT_SECRET", ""),
    )
    if not token:
        pytest.skip("LANE_EVAL_AGENT_SECRET not set or Keycloak rejected it")
    return token


@pytest.fixture()
async def trust_boundary_fixture_token(preconditions):
    """A valid token whose agent has can_call=[] -- a real, unmodified
    non-edge into commercial-normalization-agent."""
    token = await _client_credentials_token(
        "trust-boundary-fixture-agent-svc", os.environ.get("TRUST_BOUNDARY_FIXTURE_SECRET", ""),
    )
    if not token:
        pytest.skip("TRUST_BOUNDARY_FIXTURE_SECRET not set or Keycloak rejected it")
    return token


@pytest.fixture()
def tms_mcp_client(preconditions, real_directory_entities_loaded):
    tms_app = build_tms_mcp_app(root=RFQ_ROOT, cedar_url=CEDAR_URL)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=tms_app), base_url="http://tms-mcp.internal")


@pytest.fixture()
def lane_app(preconditions, tms_mcp_client):
    return build_lane_app(port=8204, root=RFQ_ROOT, cedar_url=CEDAR_URL, tms_mcp_client=tms_mcp_client)


@pytest.fixture()
def lane_eval_httpx_client(lane_app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=lane_app), base_url="http://lane-evaluation-agent.internal")


@pytest.fixture()
def route_app(preconditions, lane_eval_httpx_client):
    return build_route_app(
        port=8205, root=RFQ_ROOT, cedar_url=CEDAR_URL,
        lane_eval_base_url="http://lane-evaluation-agent.internal",
        lane_eval_httpx_client=lane_eval_httpx_client,
    )


@pytest.fixture()
def route_httpx_client(route_app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=route_app), base_url="http://route-decision-agent.internal")


@pytest.fixture()
def commercial_app(preconditions, route_httpx_client):
    return build_commercial_app(
        port=8206, root=RFQ_ROOT, cedar_url=CEDAR_URL,
        route_decision_base_url="http://route-decision-agent.internal",
        route_decision_httpx_client=route_httpx_client,
    )


@pytest.fixture()
async def commercial_httpx_client(commercial_app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=commercial_app), base_url="http://commercial-normalization-agent.internal") as c:
        yield c


async def _send_to_commercial_agent(client_httpx, bearer_token: str, payload: dict, skill: str = COMMERCIAL_SKILL_ID):
    from a2a.helpers.proto_helpers import get_message_text

    resolver = A2ACardResolver(client_httpx, "http://commercial-normalization-agent.internal")
    card = await resolver.get_agent_card()
    config = ClientConfig(httpx_client=client_httpx, supported_protocol_bindings=["JSONRPC"])
    client = await create_client(card, client_config=config)

    message = Message(role=Role.ROLE_USER, message_id="msg-1", parts=[Part(text=json.dumps(payload))])
    request = SendMessageRequest(message=message, metadata={"skill": skill})
    call_context = ClientCallContext(service_parameters={"Authorization": f"Bearer {bearer_token}"})

    states: list[str] = []
    artifact_text: str | None = None
    failure_text: str | None = None
    async for event in client.send_message(request, context=call_context):
        if event.HasField("task"):
            states.append(TaskState.Name(event.task.status.state))
        elif event.HasField("status_update"):
            state_name = TaskState.Name(event.status_update.status.state)
            states.append(state_name)
            if state_name == "TASK_STATE_FAILED" and event.status_update.status.HasField("message"):
                failure_text = get_message_text(event.status_update.status.message, delimiter=" ")
        elif event.HasField("artifact_update"):
            for part in event.artifact_update.artifact.parts:
                if part.HasField("text"):
                    artifact_text = part.text
    await client.close()
    return states, artifact_text, failure_text


@pytest.mark.asyncio
async def test_discovery_finds_business_skill_not_internal_call(commercial_httpx_client):
    resolver = A2ACardResolver(commercial_httpx_client, "http://commercial-normalization-agent.internal")
    card = await resolver.get_agent_card()
    skill_ids = [s.id for s in card.skills]
    assert COMMERCIAL_SKILL_ID in skill_ids
    assert "recommend-route" not in skill_ids


@pytest.mark.asyncio
async def test_4hop_permit_produces_normalized_option_with_full_evidence(commercial_httpx_client, lane_eval_token_as_root_caller):
    """lane-evaluation-agent (real caller, real edge) -> commercial-
    normalization-agent: permit -> route-decision-agent: permit
    (agents/catalog.yaml's pre-existing edge) -> lane-evaluation-agent
    (again, as a leaf MCP-fronting agent): permit -> tms-mcp: permit.
    Three independent Cedar delegation decisions plus one MCP decision,
    four independently constructed apps, correct outcome, real capacity
    evidence surviving all the way to the root artifact."""
    states, artifact_text, failure_text = await _send_to_commercial_agent(
        commercial_httpx_client, lane_eval_token_as_root_caller, {"route_id": ROUTE_ID},
    )
    assert states[:3] == ["TASK_STATE_SUBMITTED", "TASK_STATE_WORKING", "TASK_STATE_COMPLETED"], failure_text
    assert artifact_text is not None
    option = json.loads(artifact_text)
    assert option["route_id"] == ROUTE_ID
    assert option["status"] == "normalized"
    assert option["authorized_as"] == "agent.commercial-normalization"
    assert option["route_recommendation"]["decision"] == "recommend"
    assert option["route_recommendation"]["capacity_evidence"]["authorized_as"] == "agent.lane-evaluation"


@pytest.mark.asyncio
async def test_root_hop_deny_downstream_never_contacted(commercial_httpx_client, trust_boundary_fixture_token, route_httpx_client, monkeypatch):
    """agent.trust-boundary-fixture (valid token, can_call=[]) is denied
    at the very first boundary -- route-decision-agent (and everything
    beneath it) must never be contacted."""
    def _must_not_be_called(*a, **kw):
        raise AssertionError("route-decision-agent must not be contacted when the root A2A boundary denies")
    monkeypatch.setattr(route_httpx_client, "post", _must_not_be_called)
    monkeypatch.setattr(route_httpx_client, "get", _must_not_be_called)

    states, artifact_text, failure_text = await _send_to_commercial_agent(
        commercial_httpx_client, trust_boundary_fixture_token, {"route_id": ROUTE_ID},
    )
    assert states[:3] == ["TASK_STATE_SUBMITTED", "TASK_STATE_WORKING", "TASK_STATE_FAILED"]
    assert artifact_text is None


@pytest.mark.asyncio
async def test_business_failure_propagates_through_all_hops(commercial_httpx_client, lane_eval_token_as_root_caller):
    """A real business condition (unknown route_id -> mock-tms 404 -> tms-
    mcp 404 -> lane-evaluation-agent child task fails -> route-decision-
    agent's task fails -> commercial-normalization-agent's task fails),
    NOT an authorization mutation. The failure reason must survive three
    hops of propagation, not be swallowed into a generic error at any
    layer."""
    states, artifact_text, failure_text = await _send_to_commercial_agent(
        commercial_httpx_client, lane_eval_token_as_root_caller, {"route_id": UNKNOWN_ROUTE_ID},
    )
    assert states[-1] == "TASK_STATE_FAILED"
    assert artifact_text is None
    assert failure_text is not None and UNKNOWN_ROUTE_ID in failure_text


@pytest.mark.asyncio
async def test_unknown_skill_rejected_before_any_downstream_call(commercial_httpx_client, lane_eval_token_as_root_caller, route_httpx_client, monkeypatch):
    """A valid, permitted caller requesting an undeclared skill is
    rejected before route-decision-agent is ever contacted -- the card
    only advertises normalize-route-cost."""
    def _must_not_be_called(*a, **kw):
        raise AssertionError("route-decision-agent must not be contacted for an unsupported skill")
    monkeypatch.setattr(route_httpx_client, "post", _must_not_be_called)
    monkeypatch.setattr(route_httpx_client, "get", _must_not_be_called)

    states, artifact_text, failure_text = await _send_to_commercial_agent(
        commercial_httpx_client, lane_eval_token_as_root_caller, {"route_id": ROUTE_ID}, skill="not-a-real-skill",
    )
    assert states[-1] == "TASK_STATE_FAILED"
    assert artifact_text is None
