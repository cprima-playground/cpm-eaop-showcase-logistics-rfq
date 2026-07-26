"""M5a / Integration Checkpoint 2: route-decision-agent (A2A client) ->
lane-evaluation-agent (A2A server) -> tms-mcp (MCP) -> mock-tms.

Two distinct authorization boundaries, both real:
  Boundary 1 (A2A):  principal=caller agent, action=agent.delegate,
                      resource=agent.lane-evaluation (Cedar's existing
                      can_call-backed policy, agents/catalog.yaml)
  Boundary 2 (MCP):  principal=agent.lane-evaluation (its OWN identity,
                      never the A2A caller's), action=capacity.check,
                      context.executing_workload=workload.tms-mcp (M6a,
                      unchanged)

No layer's *code* is mocked: real Keycloak tokens + introspection, real
cedar-agent, real mock-tms (already-running live process, :8004), real
lane-evaluation-agent A2A server code, real tms-mcp code. The only
collapsed hop is transport between the two in-process FastAPI apps
(lane-evaluation-agent, tms-mcp), each mounted via httpx.ASGITransport --
same posture test_capacity_checkpoint.py already established for tms-mcp
itself; mock-tms beneath both stays genuinely over-the-wire.

Skips (not fails) if Keycloak, cedar-agent, or mock-tms aren't reachable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

RFQ_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RFQ_ROOT / "src" / "mock-tms"))
sys.path.insert(0, str(RFQ_ROOT / "src" / "tms-mcp"))
sys.path.insert(0, str(RFQ_ROOT))

from a2a.client import A2ACardResolver, ClientConfig, create_client  # noqa: E402
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState  # noqa: E402

from lane_evaluation_agent.api import build_app as build_lane_app  # noqa: E402
from lane_evaluation_agent.executor import SKILL_ID  # noqa: E402
from tms_mcp.api import build_app as build_tms_mcp_app  # noqa: E402

KEYCLOAK_URL = "http://localhost:8081"
CEDAR_URL = "http://localhost:8280"
TMS_URL = "http://127.0.0.1:8004"
ROUTE_ID = "SHA-HAM-MUC"


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
    (several test files push small ad hoc fixture entity sets). This
    module's permit/deny cases depend on the REAL agent.delegate can_call
    edge (route-decision -> lane-evaluation), so it must seed the real
    directory itself -- same pattern test_pep_delegation_checkpoint.py /
    src/route-decision-agent/tests/test_second_hop_deny.py already use.
    Found the hard way: this suite passed only by accident of test-run
    ORDER before this fixture existed (see src/route-decision-agent's
    equivalent fixture for the full incident)."""
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
async def route_decision_token(preconditions):
    import os
    token = await _client_credentials_token("route-decision-agent-svc", os.environ.get("ROUTE_DECISION_AGENT_SECRET", ""))
    if not token:
        pytest.skip("ROUTE_DECISION_AGENT_SECRET not set or Keycloak rejected it")
    return token


@pytest.fixture()
async def trust_boundary_fixture_token(preconditions):
    import os
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
async def lane_httpx_client(lane_app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=lane_app), base_url="http://lane-evaluation-agent.internal") as c:
        yield c


async def _send_and_collect(client_httpx, bearer_token: str, payload: dict, skill: str = SKILL_ID):
    resolver = A2ACardResolver(client_httpx, "http://lane-evaluation-agent.internal")
    card = await resolver.get_agent_card()

    client_httpx.headers["Authorization"] = f"Bearer {bearer_token}"
    config = ClientConfig(httpx_client=client_httpx, supported_protocol_bindings=["JSONRPC"])
    client = await create_client(card, client_config=config)

    message = Message(
        role=Role.ROLE_USER,
        message_id="msg-1",
        parts=[Part(text=json.dumps(payload))],
    )
    request = SendMessageRequest(message=message, metadata={"skill": skill})

    states: list[str] = []
    artifact_text: str | None = None
    async for event in client.send_message(request):
        if event.HasField("task"):
            states.append(TaskState.Name(event.task.status.state))
        elif event.HasField("status_update"):
            states.append(TaskState.Name(event.status_update.status.state))
        elif event.HasField("artifact_update"):
            for part in event.artifact_update.artifact.parts:
                if part.HasField("text"):
                    artifact_text = part.text

    await client.close()
    return card, states, artifact_text


@pytest.mark.asyncio
async def test_discovery_finds_business_skill_not_mcp_tool(lane_httpx_client):
    """route-decision-agent (in spirit -- discovery itself is unauthenticated,
    per the A2A spec's public Agent Card) fetches lane-evaluation-agent's
    Agent Card and finds evaluate-lane-capacity, not check_lane_capacity."""
    resolver = A2ACardResolver(lane_httpx_client, "http://lane-evaluation-agent.internal")
    card = await resolver.get_agent_card()
    skill_ids = [s.id for s in card.skills]
    assert SKILL_ID in skill_ids
    assert "check_lane_capacity" not in skill_ids


@pytest.mark.asyncio
async def test_permit_a2a_and_mcp_both_pass_task_completes(lane_httpx_client, route_decision_token):
    """route-decision-agent has can_call=[lane-evaluation-agent]
    (agents/catalog.yaml) -> Cedar permits agent.delegate (Boundary 1) ->
    lane-evaluation-agent calls tms-mcp as ITSELF -> Cedar permits
    capacity.check (Boundary 2, unchanged from M6a) -> task completes with
    a real capacity artifact. Lifecycle proven: submitted -> working ->
    completed."""
    card, states, artifact_text = await _send_and_collect(
        lane_httpx_client, route_decision_token, {"route_id": ROUTE_ID},
    )
    assert states[:3] == ["TASK_STATE_SUBMITTED", "TASK_STATE_WORKING", "TASK_STATE_COMPLETED"]
    assert artifact_text is not None
    body = json.loads(artifact_text)
    assert body["route_id"] == ROUTE_ID
    assert body["authorized_as"] == "agent.lane-evaluation"


@pytest.mark.asyncio
async def test_a2a_deny_before_any_mcp_call(lane_httpx_client, trust_boundary_fixture_token, tms_mcp_client, monkeypatch):
    """agent.trust-boundary-fixture is a VALID caller (real token) but has
    no can_call edge to agent.lane-evaluation -- Cedar denies agent.delegate
    (Boundary 1) before tms-mcp is ever reached. Lifecycle: submitted ->
    working -> failed."""
    def _must_not_be_called(*a, **kw):
        raise AssertionError("tms-mcp must not be called when the A2A boundary denies")
    monkeypatch.setattr(httpx.AsyncClient, "post", lambda self, *a, **kw: _must_not_be_called())

    card, states, artifact_text = await _send_and_collect(
        lane_httpx_client, trust_boundary_fixture_token, {"route_id": ROUTE_ID},
    )
    assert states[:3] == ["TASK_STATE_SUBMITTED", "TASK_STATE_WORKING", "TASK_STATE_FAILED"]
    assert artifact_text is None


@pytest.mark.asyncio
async def test_unknown_skill_rejected_before_any_mcp_call(lane_httpx_client, route_decision_token, tms_mcp_client, monkeypatch):
    """A valid, A2A-permitted caller requesting an undeclared skill must be
    rejected without ever reaching tms-mcp -- the card only advertises
    evaluate-lane-capacity."""
    def _must_not_be_called(*a, **kw):
        raise AssertionError("tms-mcp must not be called for an unsupported skill")
    monkeypatch.setattr(httpx.AsyncClient, "post", lambda self, *a, **kw: _must_not_be_called())

    card, states, artifact_text = await _send_and_collect(
        lane_httpx_client, route_decision_token, {"route_id": ROUTE_ID}, skill="not-a-real-skill",
    )
    assert states[-1] == "TASK_STATE_FAILED"
    assert artifact_text is None
