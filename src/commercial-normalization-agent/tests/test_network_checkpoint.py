"""Checkpoint 4: the first full 4-hop chain over REAL independent
processes and real network sockets --

  lane-evaluation-agent (real caller) -A2A-> commercial-normalization-agent
      -A2A-> route-decision-agent -A2A-> lane-evaluation-agent
      -MCP-> tms-mcp -> mock-tms

tms-mcp, lane-evaluation-agent, route-decision-agent, and
commercial-normalization-agent are ALL started as real `uv run`
subprocesses on real TCP ports, wired together via
LANE_EVAL_AGENT_URL/TMS_MCP_URL/ROUTE_DECISION_AGENT_URL env vars, same
as a real deployment. This file knows only
COMMERCIAL_NORMALIZATION_AGENT_URL (the http://host:port it starts
itself) -- it never imports any of the 4 packages' app/executor modules
directly. mock-tms is the already-running live process, :8004.

Learned from the earlier Checkpoint 2/2b correction: a claim about
independently-running services is only proven at THIS level, not at the
in-process ASGITransport level test_a2a_chain_checkpoint.py uses -- so
Checkpoint 4 is defined here, at the network level, directly (no
"Checkpoint 4a" SDK-only substitute).

Mechanical extension of route-decision-agent's own
test_network_checkpoint.py pattern one hop further -- same helpers, same
Windows taskkill/stdout-drain handling, nothing new architecturally.

Skips if Keycloak/cedar-agent/mock-tms aren't reachable, or if `uv run`
can't boot a subprocess (surfaces as a hard failure, not a skip -- process
boot itself is part of what this file proves).
"""

from __future__ import annotations

import asyncio
import collections
import json
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx
import pytest

RFQ_ROOT = Path(__file__).resolve().parents[3]
TMS_MCP_DIR = RFQ_ROOT / "src" / "tms-mcp"
LANE_AGENT_DIR = RFQ_ROOT / "src" / "lane-evaluation-agent"
ROUTE_AGENT_DIR = RFQ_ROOT / "src" / "route-decision-agent"
COMMERCIAL_AGENT_DIR = RFQ_ROOT / "src" / "commercial-normalization-agent"

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


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _drain(proc: subprocess.Popen, buf: collections.deque) -> None:
    try:
        for line in proc.stdout:
            buf.append(line)
    except Exception:
        pass


def _start_server(cwd: Path, script: str, env: dict, ready_url: str, timeout: float = 45.0) -> subprocess.Popen:
    proc = subprocess.Popen(
        ["uv", "run", script],
        cwd=str(cwd), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        bufsize=1,
    )
    buf: collections.deque = collections.deque(maxlen=500)
    proc._output_buf = buf  # type: ignore[attr-defined]
    drain_thread = threading.Thread(target=_drain, args=(proc, buf), daemon=True)
    drain_thread.start()

    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"{script} exited early (code {proc.returncode}) before becoming ready:\n{''.join(buf)}")
        try:
            if httpx.get(ready_url, timeout=1.0).status_code == 200:
                return proc
        except Exception:
            pass
        time.sleep(0.3)
    _stop_server(proc)
    raise TimeoutError(f"{script} did not become ready at {ready_url} within {timeout}s. Captured output:\n{''.join(buf)}")


def _stop_server(proc: subprocess.Popen) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
        )
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        return

    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


@pytest.fixture(scope="module")
def preconditions():
    if not (_keycloak_up() and _cedar_up() and _tms_up()):
        pytest.skip("Keycloak (:8081), cedar-agent (:8280), or mock-tms (:8004) not running")


@pytest.fixture(scope="module")
def real_directory_entities_loaded(preconditions):
    sys.path.insert(0, str(RFQ_ROOT))
    import yaml
    from rfq_common.pdp import DataAdmin, PolicyAdmin, PolicyBundle, SchemaAdmin, generate_schema
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


@pytest.fixture(scope="module")
def tms_mcp_server(real_directory_entities_loaded):
    port = _free_port()
    env = {
        **os.environ,
        "A2A_PORT": str(port),
        "CEDAR_URL": CEDAR_URL,
        "TMS_MCP_CLIENT_SECRET": os.environ.get("TMS_MCP_CLIENT_SECRET", ""),
        "TMS_API_KEY": os.environ.get("TMS_API_KEY", ""),
        "TMS_URL": TMS_URL,
    }
    proc = _start_server(TMS_MCP_DIR, "tms-mcp", env, f"http://127.0.0.1:{port}/healthz")
    yield f"http://127.0.0.1:{port}"
    _stop_server(proc)


@pytest.fixture(scope="module")
def lane_agent_server(tms_mcp_server):
    port = _free_port()
    env = {
        **os.environ,
        "A2A_PORT": str(port),
        "CEDAR_URL": CEDAR_URL,
        "TMS_MCP_URL": tms_mcp_server,
        "LANE_EVAL_AGENT_SECRET": os.environ.get("LANE_EVAL_AGENT_SECRET", ""),
    }
    proc = _start_server(LANE_AGENT_DIR, "lane-evaluation-agent", env, f"http://127.0.0.1:{port}/healthz")
    yield f"http://127.0.0.1:{port}"
    _stop_server(proc)


@pytest.fixture(scope="module")
def route_agent_server(lane_agent_server):
    port = _free_port()
    env = {
        **os.environ,
        "A2A_PORT": str(port),
        "CEDAR_URL": CEDAR_URL,
        "LANE_EVAL_AGENT_URL": lane_agent_server,
        "ROUTE_DECISION_AGENT_SECRET": os.environ.get("ROUTE_DECISION_AGENT_SECRET", ""),
    }
    proc = _start_server(ROUTE_AGENT_DIR, "route-decision-agent", env, f"http://127.0.0.1:{port}/healthz")
    yield f"http://127.0.0.1:{port}"
    _stop_server(proc)


@pytest.fixture()
def commercial_agent_server(route_agent_server):
    """Function-scoped -- the restart test needs to stop/restart this
    specific process without affecting other tests in this module."""
    port = _free_port()
    env = {
        **os.environ,
        "A2A_PORT": str(port),
        "CEDAR_URL": CEDAR_URL,
        "ROUTE_DECISION_AGENT_URL": route_agent_server,
        "COMMERCIAL_NORM_AGENT_SECRET": os.environ.get("COMMERCIAL_NORM_AGENT_SECRET", ""),
    }
    proc = _start_server(COMMERCIAL_AGENT_DIR, "commercial-normalization-agent", env, f"http://127.0.0.1:{port}/healthz")
    url = f"http://127.0.0.1:{port}"
    yield proc, url
    _stop_server(proc)


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
    token = await _client_credentials_token("lane-evaluation-agent-svc", os.environ.get("LANE_EVAL_AGENT_SECRET", ""))
    if not token:
        pytest.skip("LANE_EVAL_AGENT_SECRET not set or Keycloak rejected it")
    return token


@pytest.fixture()
async def trust_boundary_fixture_token(preconditions):
    token = await _client_credentials_token("trust-boundary-fixture-agent-svc", os.environ.get("TRUST_BOUNDARY_FIXTURE_SECRET", ""))
    if not token:
        pytest.skip("TRUST_BOUNDARY_FIXTURE_SECRET not set or Keycloak rejected it")
    return token


async def _send_to_commercial_agent(url: str, bearer_token: str, payload: dict, correlation_hint: str | None = None):
    from a2a.client import A2ACardResolver, ClientConfig, create_client
    from a2a.client.client import ClientCallContext
    from a2a.helpers.proto_helpers import get_message_text
    from a2a.types import Message, Part, Role, SendMessageRequest, TaskState

    async with httpx.AsyncClient(timeout=30.0) as client_httpx:  # real network transport; 30s not httpx's 5s default -- concurrent real 4-hop calls (esp. with M5.9's OTel instrumentation now on every hop) can genuinely exceed 5s
        resolver = A2ACardResolver(client_httpx, url)
        card = await resolver.get_agent_card()
        config = ClientConfig(httpx_client=client_httpx, supported_protocol_bindings=["JSONRPC"])
        client = await create_client(card, client_config=config)

        message_id = correlation_hint or str(uuid.uuid4())
        message = Message(role=Role.ROLE_USER, message_id=message_id, parts=[Part(text=json.dumps(payload))])
        request = SendMessageRequest(message=message, metadata={"skill": "normalize-route-cost"})
        call_context = ClientCallContext(service_parameters={"Authorization": f"Bearer {bearer_token}"})

        states: list[str] = []
        artifact_text: str | None = None
        failure_text: str | None = None
        context_ids: set[str] = set()
        async for event in client.send_message(request, context=call_context):
            if event.HasField("task"):
                states.append(TaskState.Name(event.task.status.state))
                if event.task.context_id:
                    context_ids.add(event.task.context_id)
            elif event.HasField("status_update"):
                state_name = TaskState.Name(event.status_update.status.state)
                states.append(state_name)
                if event.status_update.context_id:
                    context_ids.add(event.status_update.context_id)
                if state_name == "TASK_STATE_FAILED" and event.status_update.status.HasField("message"):
                    failure_text = get_message_text(event.status_update.status.message, delimiter=" ")
            elif event.HasField("artifact_update"):
                for part in event.artifact_update.artifact.parts:
                    if part.HasField("text"):
                        artifact_text = part.text
        await client.close()
    return states, artifact_text, failure_text, context_ids


def test_server_boots_and_agent_card_is_retrievable_over_real_http(commercial_agent_server):
    """Real subprocess, real bound TCP port -- proves commercial-
    normalization-agent itself boots and its Agent Card advertises the
    business skill (normalize-route-cost), not the recommend-route A2A
    call it uses internally."""
    proc, url = commercial_agent_server
    assert proc.poll() is None, "server process must still be running"
    r = httpx.get(f"{url}/.well-known/agent-card.json", timeout=5.0)
    assert r.status_code == 200
    card = r.json()
    skill_ids = [s["id"] for s in card["skills"]]
    assert "normalize-route-cost" in skill_ids
    assert url.split("//")[1] in card["supportedInterfaces"][0]["url"]


@pytest.mark.asyncio
async def test_real_network_4hop_permit(commercial_agent_server, lane_eval_token_as_root_caller):
    """The full chain, all 4 services real independent processes, real
    TCP sockets throughout: lane-evaluation-agent (real caller) ->
    commercial-normalization-agent -> route-decision-agent ->
    lane-evaluation-agent (again, as leaf) -> tms-mcp -> mock-tms. Real
    capacity evidence must survive all 3 A2A hops plus the MCP call into
    the root artifact."""
    proc, url = commercial_agent_server
    states, artifact_text, failure_text, _ = await _send_to_commercial_agent(url, lane_eval_token_as_root_caller, {"route_id": ROUTE_ID})
    assert states[:3] == ["TASK_STATE_SUBMITTED", "TASK_STATE_WORKING", "TASK_STATE_COMPLETED"], failure_text
    assert artifact_text is not None
    option = json.loads(artifact_text)
    assert option["route_id"] == ROUTE_ID
    assert option["status"] == "normalized"
    assert option["authorized_as"] == "agent.commercial-normalization"
    assert option["route_recommendation"]["decision"] == "recommend"
    assert option["route_recommendation"]["capacity_evidence"]["authorized_as"] == "agent.lane-evaluation"


@pytest.mark.asyncio
async def test_real_network_root_hop_deny(commercial_agent_server, trust_boundary_fixture_token):
    """agent.trust-boundary-fixture (real token, can_call=[]) over a real
    socket -- denied at the very first boundary. No visibility into the
    server's internals here (network boundary) -- proven by the
    observable outcome only, same tradeoff as every other network-level
    deny test in this repo."""
    proc, url = commercial_agent_server
    states, artifact_text, failure_text, _ = await _send_to_commercial_agent(url, trust_boundary_fixture_token, {"route_id": ROUTE_ID})
    assert states[:3] == ["TASK_STATE_SUBMITTED", "TASK_STATE_WORKING", "TASK_STATE_FAILED"]
    assert artifact_text is None


@pytest.mark.asyncio
async def test_real_network_business_failure_propagates_through_all_hops(commercial_agent_server, lane_eval_token_as_root_caller):
    """Real business condition (unknown route_id) 404s through mock-tms
    -> tms-mcp -> lane-evaluation-agent -> route-decision-agent ->
    commercial-normalization-agent, all real processes, all real
    sockets. The reason must still be present at the root, not swallowed
    at any hop."""
    proc, url = commercial_agent_server
    states, artifact_text, failure_text, _ = await _send_to_commercial_agent(url, lane_eval_token_as_root_caller, {"route_id": UNKNOWN_ROUTE_ID})
    assert states[-1] == "TASK_STATE_FAILED"
    assert artifact_text is None
    assert failure_text is not None and UNKNOWN_ROUTE_ID in failure_text


@pytest.mark.asyncio
async def test_concurrent_root_tasks_do_not_cross_over(commercial_agent_server, lane_eval_token_as_root_caller):
    """Two simultaneous root A2A calls into the SAME running
    commercial-normalization-agent process, distinct message ids
    (correlation), one permitted route and one that fails on a real
    business condition -- both must resolve independently, with no
    result crossover (task A's artifact must never contain task B's
    route_id or vice versa) despite sharing the same underlying process,
    task store, and downstream agent/MCP chain."""
    proc, url = commercial_agent_server
    call_a = _send_to_commercial_agent(url, lane_eval_token_as_root_caller, {"route_id": ROUTE_ID}, correlation_hint=str(uuid.uuid4()))
    call_b = _send_to_commercial_agent(url, lane_eval_token_as_root_caller, {"route_id": UNKNOWN_ROUTE_ID}, correlation_hint=str(uuid.uuid4()))
    (states_a, artifact_a, failure_a, ctx_a), (states_b, artifact_b, failure_b, ctx_b) = await asyncio.gather(call_a, call_b)

    assert states_a[-1] == "TASK_STATE_COMPLETED", failure_a
    assert artifact_a is not None
    option_a = json.loads(artifact_a)
    assert option_a["route_id"] == ROUTE_ID

    assert states_b[-1] == "TASK_STATE_FAILED"
    assert artifact_b is None
    assert failure_b is not None and UNKNOWN_ROUTE_ID in failure_b

    # No crossover: each task's own context id(s) are disjoint from the other's.
    assert ctx_a.isdisjoint(ctx_b), f"context ids leaked across concurrent tasks: {ctx_a} vs {ctx_b}"
    # And task A's success artifact never mentions task B's route id, or vice versa.
    assert UNKNOWN_ROUTE_ID not in artifact_a


def test_restart_behavior(commercial_agent_server):
    """commercial-normalization-agent stops -> call against its dead port
    fails clearly -> restarted -> discovery works again. Downstream
    route-decision-agent/lane-evaluation-agent/tms-mcp stay up throughout
    (module-scoped) -- isolates the restart proof to this outermost hop."""
    proc, url = commercial_agent_server
    _stop_server(proc)
    assert proc.poll() is not None, "process must have actually exited before this assertion"

    try:
        r = httpx.get(f"{url}/healthz", timeout=2.0)
        pytest.fail(f"expected the stopped server's port to refuse connections, got HTTP {r.status_code}: {r.text!r}")
    except httpx.TransportError:
        pass

    port = int(url.rsplit(":", 1)[1])
    env = {**os.environ, "A2A_HOST": "127.0.0.1", "A2A_PORT": str(port)}
    new_proc = _start_server(COMMERCIAL_AGENT_DIR, "commercial-normalization-agent", env, f"{url}/healthz")
    try:
        r = httpx.get(f"{url}/.well-known/agent-card.json", timeout=5.0)
        assert r.status_code == 200
        assert "normalize-route-cost" in [s["id"] for s in r.json()["skills"]]
    finally:
        _stop_server(new_proc)
