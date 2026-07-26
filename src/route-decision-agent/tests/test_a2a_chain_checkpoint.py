"""M5b / Integration Checkpoint 3: 3-hop chain proving agent -> agent ->
agent -> MCP, not just one isolated A2A server:

  commercial-normalization-agent -A2A-> route-decision-agent
      -A2A-> lane-evaluation-agent -MCP-> tms-mcp -> mock-tms

Each hop authenticates and authorizes its IMMEDIATE caller only.
agent.commercial-normalization is never propagated as the Cedar principal
past hop 1; agent.route-decision is never propagated past hop 2 (rides
along only as `root_requester`/provenance, verified by nobody downstream --
same posture as delegated_by, M4a).

No layer's code is mocked. Real Keycloak tokens + introspection (3 real
client-credentials grants: commercial-normalization-agent-svc,
route-decision-agent-svc, and for the deny case lane-evaluation-agent-svc),
real cedar-agent, real mock-tms (already-running live process, :8004).
route-decision-agent, lane-evaluation-agent, and tms-mcp are each mounted
in-process via httpx.ASGITransport -- same posture M6a/M5a already
established.
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
sys.path.insert(0, str(RFQ_ROOT))

from a2a.client import A2ACardResolver, ClientConfig, create_client  # noqa: E402
from a2a.client.client import ClientCallContext  # noqa: E402
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState  # noqa: E402

from lane_evaluation_agent.api import build_app as build_lane_app  # noqa: E402
from route_decision_agent.api import build_app as build_route_app  # noqa: E402
from route_decision_agent.executor import SKILL_ID as ROUTE_SKILL_ID  # noqa: E402
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
    """cedar-agent is a shared sidecar across every test module in this
    repo -- whatever entities were pushed LAST (by whichever suite ran
    most recently) are what's loaded, not necessarily the real directory
    (several other test files push small ad hoc fixture entity sets).
    This module talks to real agent-to-agent can_call edges
    (commercial-normalization -> route-decision, route-decision ->
    lane-evaluation), so it must seed the REAL directory itself, same
    pattern as test_second_hop_deny.py / test_pep_delegation_checkpoint.py
    -- never assume ambient state left by an unrelated earlier test run."""
    import yaml
    from rfq_common.pdp import DataAdmin, PolicyAdmin, SchemaAdmin, generate_schema
    from tools.identity.gen_cedar_entities import generate_cedar_entities
    from tools.identity.validator import validate_identity

    projection = yaml.safe_load((RFQ_ROOT / "authorization" / "authz-projection.yaml").read_text(encoding="utf-8"))
    actions_doc = yaml.safe_load((RFQ_ROOT / "business" / "actions.yaml").read_text(encoding="utf-8"))
    schema = generate_schema(projection, actions_doc)
    bundle = __import__("rfq_common.pdp", fromlist=["PolicyBundle"]).PolicyBundle.from_path(
        RFQ_ROOT / "authorization" / "policies.cedar"
    )

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
async def commercial_norm_token(preconditions):
    token = await _client_credentials_token(
        "commercial-normalization-agent-svc", os.environ.get("COMMERCIAL_NORM_AGENT_SECRET", ""),
    )
    if not token:
        pytest.skip("COMMERCIAL_NORM_AGENT_SECRET not set or Keycloak rejected it")
    return token


@pytest.fixture()
async def lane_eval_token_as_caller(preconditions):
    """lane-evaluation-agent's OWN token, used here as an unauthorized
    CALLER of route-decision-agent -- lane-evaluation-agent.can_call does
    NOT include route-decision-agent (agents/catalog.yaml), a real,
    unmodified non-edge -- first-hop deny fixture."""
    token = await _client_credentials_token(
        "lane-evaluation-agent-svc", os.environ.get("LANE_EVAL_AGENT_SECRET", ""),
    )
    if not token:
        pytest.skip("LANE_EVAL_AGENT_SECRET not set or Keycloak rejected it")
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
async def route_httpx_client(route_app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=route_app), base_url="http://route-decision-agent.internal") as c:
        yield c


async def _send_to_route_agent(client_httpx, bearer_token: str, payload: dict, skill: str = ROUTE_SKILL_ID):
    resolver = A2ACardResolver(client_httpx, "http://route-decision-agent.internal")
    card = await resolver.get_agent_card()
    config = ClientConfig(httpx_client=client_httpx, supported_protocol_bindings=["JSONRPC"])
    client = await create_client(card, client_config=config)

    message = Message(role=Role.ROLE_USER, message_id="msg-1", parts=[Part(text=json.dumps(payload))])
    request = SendMessageRequest(message=message, metadata={"skill": skill})
    call_context = ClientCallContext(service_parameters={"Authorization": f"Bearer {bearer_token}"})

    states: list[str] = []
    artifact_text: str | None = None
    failure_text: str | None = None
    from a2a.helpers.proto_helpers import get_message_text

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
async def test_multi_hop_permit_produces_recommendation_with_capacity_evidence(route_httpx_client, commercial_norm_token):
    """commercial-normalization-agent (real token) -> route-decision-agent:
    permit (can_call edge, agents/catalog.yaml, pre-existing) -> A2A call to
    lane-evaluation-agent as agent.route-decision's OWN identity: permit
    (M5a's edge) -> MCP call to tms-mcp as agent.lane-evaluation's OWN
    identity: permit (M6a's D10) -> recommendation artifact includes real
    capacity evidence from mock-tms. Two independent Cedar decisions, two
    independent A2A tasks (parent + child), correct outcome."""
    states, artifact_text, failure_text = await _send_to_route_agent(
        route_httpx_client, commercial_norm_token, {"route_id": ROUTE_ID},
    )
    assert states[:3] == ["TASK_STATE_SUBMITTED", "TASK_STATE_WORKING", "TASK_STATE_COMPLETED"], failure_text
    assert artifact_text is not None
    recommendation = json.loads(artifact_text)
    assert recommendation["route_id"] == ROUTE_ID
    assert recommendation["decision"] == "recommend"
    assert recommendation["capacity_evidence"]["route_id"] == ROUTE_ID
    assert recommendation["capacity_evidence"]["authorized_as"] == "agent.lane-evaluation"
    assert "capacity_status" in recommendation["capacity_evidence"]


@pytest.mark.asyncio
async def test_first_hop_deny_lane_evaluation_never_contacted(route_httpx_client, lane_eval_token_as_caller, lane_eval_httpx_client, monkeypatch):
    """lane-evaluation-agent is a VALID caller (real token) but is NOT in
    route-decision-agent's can_call list -- Cedar denies agent.delegate at
    hop 1, before lane-evaluation-agent (hop 2) is ever contacted."""
    def _must_not_be_called(*a, **kw):
        raise AssertionError("lane-evaluation-agent must not be contacted when hop 1 denies")
    # patch the INSTANCE bound to lane-evaluation-agent only -- route_httpx_client
    # (a different instance) still needs a working .get/.post for its own
    # request to route-decision-agent.
    monkeypatch.setattr(lane_eval_httpx_client, "post", _must_not_be_called)
    monkeypatch.setattr(lane_eval_httpx_client, "get", _must_not_be_called)

    states, artifact_text, failure_text = await _send_to_route_agent(
        route_httpx_client, lane_eval_token_as_caller, {"route_id": ROUTE_ID},
    )
    assert states[:3] == ["TASK_STATE_SUBMITTED", "TASK_STATE_WORKING", "TASK_STATE_FAILED"]
    assert artifact_text is None


@pytest.mark.asyncio
async def test_child_task_failure_propagates_to_parent(route_httpx_client, commercial_norm_token):
    """Real business condition (unknown route_id -> mock-tms 404 -> tms-mcp
    404 -> lane-evaluation-agent's child task fails), NOT an authorization
    mutation. route-decision-agent's parent task must observe the child
    failure and fail itself with the reason retained -- not silently
    succeed with an empty/garbage recommendation."""
    states, artifact_text, failure_text = await _send_to_route_agent(
        route_httpx_client, commercial_norm_token, {"route_id": UNKNOWN_ROUTE_ID},
    )
    assert states[-1] == "TASK_STATE_FAILED"
    assert artifact_text is None
    assert failure_text is not None and UNKNOWN_ROUTE_ID in failure_text


@pytest.mark.asyncio
async def test_unknown_downstream_skill_rejected_by_child(preconditions, commercial_norm_token, lane_eval_httpx_client, tms_mcp_client):
    """route-decision-agent (bug/version-mismatch injected here via the
    child_skill override -- a constructor knob, same shape as tms_mcp_client
    injection, not a protocol hack) requests an undeclared skill from
    lane-evaluation-agent -- child rejects it (lane_evaluation_agent's own
    skill != SKILL_ID check, unchanged), parent task reflects the failure."""
    route_app = build_route_app(
        port=8205, root=RFQ_ROOT, cedar_url=CEDAR_URL,
        lane_eval_base_url="http://lane-evaluation-agent.internal",
        lane_eval_httpx_client=lane_eval_httpx_client,
        child_skill="not-a-real-lane-skill",
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=route_app), base_url="http://route-decision-agent.internal") as client_httpx:
        states, artifact_text, failure_text = await _send_to_route_agent(
            client_httpx, commercial_norm_token, {"route_id": ROUTE_ID},
        )
    assert states[-1] == "TASK_STATE_FAILED"
    assert artifact_text is None
