"""Checkpoint 2b, extended to the 3-hop chain: route-decision-agent as an
INDEPENDENTLY RUNNING process, itself calling an independently running
lane-evaluation-agent, itself calling an independently running tms-mcp --
not the in-process ASGITransport shortcuts test_a2a_chain_checkpoint.py /
test_second_hop_deny.py (Checkpoint 3, protocol-level integration) use.

This file knows only ROUTE_DECISION_AGENT_URL (an http://host:port it
starts itself) -- it never imports route_decision_agent's, lane_evaluation
_agent's, or tms_mcp's app/executor modules directly. All three services
are started as real `uv run` subprocesses on real TCP ports, wired
together via LANE_EVAL_AGENT_URL / TMS_MCP_URL env vars, same as a real
deployment would be. mock-tms is the already-running live process, :8004.

Mechanical extension of src/lane-evaluation-agent/tests/
test_network_checkpoint.py's pattern to the second hop -- same helpers,
same Windows taskkill/stdout-drain fixes, nothing new architecturally.

Skips if Keycloak/cedar-agent/mock-tms aren't reachable, or if `uv run`
can't boot a subprocess (surfaces as a hard failure, not a skip -- process
boot itself is part of what this file proves).
"""

from __future__ import annotations

import collections
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest

RFQ_ROOT = Path(__file__).resolve().parents[3]
TMS_MCP_DIR = RFQ_ROOT / "src" / "tms-mcp"
LANE_AGENT_DIR = RFQ_ROOT / "src" / "lane-evaluation-agent"
ROUTE_AGENT_DIR = RFQ_ROOT / "src" / "route-decision-agent"

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
    """Must run continuously -- see lane-evaluation-agent's identical
    helper: unread stdout PIPE deadlocks the child once the OS buffer
    fills (a2a-sdk's own startup logging is verbose enough to hit this)."""
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
    """Windows: `uv run` spawns the real uvicorn process as a nested
    child -- terminate() only kills the outer `uv` process. See
    lane-evaluation-agent's identical helper for the process-tree
    forensics that found this."""
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
    """Same rationale as the other network/chain checkpoint files --
    cedar-agent is a shared sidecar, seed the real directory explicitly."""
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
    """Module-scoped here (unlike lane-evaluation-agent's own restart
    test, which needs function scope) -- this file's restart test targets
    route-decision-agent, the outermost hop, not this one."""
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


@pytest.fixture()
def route_agent_server(lane_agent_server):
    """Function-scoped -- the restart test needs to stop/restart this
    specific process without affecting other tests in this module."""
    port = _free_port()
    env = {
        **os.environ,
        "A2A_PORT": str(port),
        "CEDAR_URL": CEDAR_URL,
        "LANE_EVAL_AGENT_URL": lane_agent_server,
        "ROUTE_DECISION_AGENT_SECRET": os.environ.get("ROUTE_DECISION_AGENT_SECRET", ""),
    }
    proc = _start_server(ROUTE_AGENT_DIR, "route-decision-agent", env, f"http://127.0.0.1:{port}/healthz")
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
async def commercial_norm_token(preconditions):
    token = await _client_credentials_token(
        "commercial-normalization-agent-svc", os.environ.get("COMMERCIAL_NORM_AGENT_SECRET", ""),
    )
    if not token:
        pytest.skip("COMMERCIAL_NORM_AGENT_SECRET not set or Keycloak rejected it")
    return token


@pytest.fixture()
async def lane_eval_token_as_caller(preconditions):
    """lane-evaluation-agent's own token, used as an unauthorized CALLER
    of route-decision-agent -- a real, unmodified non-edge (agents/
    catalog.yaml), same fixture role as test_a2a_chain_checkpoint.py's."""
    token = await _client_credentials_token(
        "lane-evaluation-agent-svc", os.environ.get("LANE_EVAL_AGENT_SECRET", ""),
    )
    if not token:
        pytest.skip("LANE_EVAL_AGENT_SECRET not set or Keycloak rejected it")
    return token


async def _send_to_route_agent(url: str, bearer_token: str, payload: dict):
    import json
    import uuid

    from a2a.client import A2ACardResolver, ClientConfig, create_client
    from a2a.client.client import ClientCallContext
    from a2a.helpers.proto_helpers import get_message_text
    from a2a.types import Message, Part, Role, SendMessageRequest, TaskState

    async with httpx.AsyncClient() as client_httpx:  # real network transport, default
        resolver = A2ACardResolver(client_httpx, url)
        card = await resolver.get_agent_card()
        config = ClientConfig(httpx_client=client_httpx, supported_protocol_bindings=["JSONRPC"])
        client = await create_client(card, client_config=config)

        message = Message(role=Role.ROLE_USER, message_id=str(uuid.uuid4()), parts=[Part(text=json.dumps(payload))])
        request = SendMessageRequest(message=message, metadata={"skill": "recommend-route"})
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


def test_server_boots_and_agent_card_is_retrievable_over_real_http(route_agent_server):
    """Real subprocess, real bound TCP port, plain httpx -- proves
    route-decision-agent itself boots and its Agent Card advertises the
    business skill (recommend-route), not the A2A/MCP internals it uses
    to satisfy it."""
    proc, url = route_agent_server
    assert proc.poll() is None, "server process must still be running"
    r = httpx.get(f"{url}/.well-known/agent-card.json", timeout=5.0)
    assert r.status_code == 200
    card = r.json()
    skill_ids = [s["id"] for s in card["skills"]]
    assert "recommend-route" in skill_ids
    assert url.split("//")[1] in card["supportedInterfaces"][0]["url"]


@pytest.mark.asyncio
async def test_real_network_3hop_permit(route_agent_server, commercial_norm_token):
    """commercial-normalization-agent (real token, real socket) ->
    route-decision-agent (real process) -A2A-> lane-evaluation-agent
    (real process) -MCP-> tms-mcp (real process) -> mock-tms (real,
    already-running). Three independently running services, two real A2A
    hops over real TCP, one real MCP call -- the full chain
    test_a2a_chain_checkpoint.py already proved at the protocol level,
    now proved over real sockets end to end."""
    proc, url = route_agent_server
    states, artifact_text, failure_text = await _send_to_route_agent(url, commercial_norm_token, {"route_id": ROUTE_ID})
    assert states[:3] == ["TASK_STATE_SUBMITTED", "TASK_STATE_WORKING", "TASK_STATE_COMPLETED"], failure_text
    assert artifact_text is not None
    import json
    recommendation = json.loads(artifact_text)
    assert recommendation["route_id"] == ROUTE_ID
    assert recommendation["decision"] == "recommend"
    assert recommendation["capacity_evidence"]["authorized_as"] == "agent.lane-evaluation"


@pytest.mark.asyncio
async def test_real_network_first_hop_deny(route_agent_server, lane_eval_token_as_caller):
    """lane-evaluation-agent's own real token used as a CALLER of
    route-decision-agent over a real socket -- not in route-decision-
    agent's can_call -- denied at hop 1, before the (real, running)
    lane-evaluation-agent process is ever contacted as hop 2. No
    visibility into the server's internals here (network boundary, same
    tradeoff as lane-evaluation-agent's own network deny test) -- proven
    by the observable outcome only."""
    proc, url = route_agent_server
    states, artifact_text, failure_text = await _send_to_route_agent(url, lane_eval_token_as_caller, {"route_id": ROUTE_ID})
    assert states[:3] == ["TASK_STATE_SUBMITTED", "TASK_STATE_WORKING", "TASK_STATE_FAILED"]
    assert artifact_text is None


def test_restart_behavior(route_agent_server):
    """route-decision-agent stops -> call against its dead port fails
    clearly -> restarted -> discovery works again. Downstream lane-
    evaluation-agent/tms-mcp stay up throughout (module-scoped) -- this
    isolates the restart proof to the outermost hop, same shape as
    lane-evaluation-agent's own restart test isolates it to that hop."""
    proc, url = route_agent_server
    _stop_server(proc)
    assert proc.poll() is not None, "process must have actually exited before this assertion"

    try:
        r = httpx.get(f"{url}/healthz", timeout=2.0)
        pytest.fail(f"expected the stopped server's port to refuse connections, got HTTP {r.status_code}: {r.text!r}")
    except httpx.TransportError:
        pass

    port = int(url.rsplit(":", 1)[1])
    env = {**os.environ, "A2A_HOST": "127.0.0.1", "A2A_PORT": str(port)}
    # lane-evaluation-agent/tms-mcp not required for this check --
    # restart + rediscovery only, not a full recommendation call.
    new_proc = _start_server(ROUTE_AGENT_DIR, "route-decision-agent", env, f"{url}/healthz")
    try:
        r = httpx.get(f"{url}/.well-known/agent-card.json", timeout=5.0)
        assert r.status_code == 200
        assert "recommend-route" in [s["id"] for s in r.json()["skills"]]
    finally:
        _stop_server(new_proc)
