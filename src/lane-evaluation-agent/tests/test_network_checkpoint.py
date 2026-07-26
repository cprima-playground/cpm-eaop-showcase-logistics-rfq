"""Checkpoint 2b: lane-evaluation-agent as an INDEPENDENTLY RUNNING
process, reached over a real network socket -- not the in-process
ASGITransport shortcut test_a2a_checkpoint.py (Checkpoint 2a, protocol-
level integration) uses.

This file knows only LANE_EVALUATION_AGENT_URL (an http://host:port it
starts itself, but never imports lane_evaluation_agent's app/executor
modules directly) -- the SDK client crosses a real process boundary the
same way an operator's client would. tms-mcp is likewise started as its
own real subprocess (a real dependency, not mocked or ASGI-mounted);
mock-tms is the already-running live process on :8004.

Skips if Keycloak/cedar-agent/mock-tms aren't reachable, or if `uv run`
can't boot a subprocess (surfaces as a hard failure, not a skip, if that
happens -- process boot itself is part of what this file proves).
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


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _drain(proc: subprocess.Popen, buf: collections.deque) -> None:
    """Must run continuously for the lifetime of the process -- an unread
    stdout PIPE deadlocks the child once the OS pipe buffer fills (a2a-sdk's
    startup logging, esp. grpc/protobuf, is verbose enough to hit this in
    practice: the child blocks on write() before it ever binds the port,
    which looks indistinguishable from "just slow" until you notice it
    never times out via proc.poll() either)."""
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
    """`uv run <script>` spawns the actual uvicorn process as a nested
    child, not an exec-replace -- on Windows, Popen.terminate() only kills
    the immediate `uv` process, leaving the real server orphaned and still
    bound to the port (confirmed the hard way: process tree inspection
    during cleanup showed paired python.exe processes per invocation).
    `taskkill /T /F` kills the whole tree; POSIX falls back to terminate()
    since process groups work correctly there."""
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
    """Same rationale as test_a2a_checkpoint.py's fixture of the same name
    -- cedar-agent is a shared sidecar; seed the real directory explicitly."""
    import sys as _sys
    _sys.path.insert(0, str(RFQ_ROOT))
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


@pytest.fixture()
def lane_agent_server(tms_mcp_server):
    """Function-scoped (not module) -- the restart-behavior test needs to
    stop and restart this specific server without affecting other tests."""
    port = _free_port()
    env = {
        **os.environ,
        "A2A_PORT": str(port),
        "CEDAR_URL": CEDAR_URL,
        "TMS_MCP_URL": tms_mcp_server,
        "LANE_EVAL_AGENT_SECRET": os.environ.get("LANE_EVAL_AGENT_SECRET", ""),
    }
    proc = _start_server(LANE_AGENT_DIR, "lane-evaluation-agent", env, f"http://127.0.0.1:{port}/healthz")
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
async def route_decision_token(preconditions):
    token = await _client_credentials_token("route-decision-agent-svc", os.environ.get("ROUTE_DECISION_AGENT_SECRET", ""))
    if not token:
        pytest.skip("ROUTE_DECISION_AGENT_SECRET not set or Keycloak rejected it")
    return token


@pytest.fixture()
async def trust_boundary_fixture_token(preconditions):
    token = await _client_credentials_token("trust-boundary-fixture-agent-svc", os.environ.get("TRUST_BOUNDARY_FIXTURE_SECRET", ""))
    if not token:
        pytest.skip("TRUST_BOUNDARY_FIXTURE_SECRET not set or Keycloak rejected it")
    return token


def test_server_boots_and_agent_card_is_retrievable_over_real_http(lane_agent_server):
    """Real subprocess, real bound TCP port, plain httpx (no ASGITransport)."""
    proc, url = lane_agent_server
    assert proc.poll() is None, "server process must still be running"
    r = httpx.get(f"{url}/.well-known/agent-card.json", timeout=5.0)
    assert r.status_code == 200
    card = r.json()
    skill_ids = [s["id"] for s in card["skills"]]
    assert "evaluate-lane-capacity" in skill_ids
    assert "check_lane_capacity" not in skill_ids
    # advertised interface URL is reachable at the address this test used --
    # not an unconditional "localhost" baked in regardless of bind target.
    assert url.split("//")[1] in card["supportedInterfaces"][0]["url"]


@pytest.mark.asyncio
async def test_real_network_permit(lane_agent_server, route_decision_token):
    import json
    import uuid

    from a2a.client import A2ACardResolver, ClientConfig, create_client
    from a2a.client.client import ClientCallContext
    from a2a.types import Message, Part, Role, SendMessageRequest, TaskState

    proc, url = lane_agent_server
    async with httpx.AsyncClient() as client_httpx:  # REAL network transport, default
        resolver = A2ACardResolver(client_httpx, url)
        card = await resolver.get_agent_card()
        config = ClientConfig(httpx_client=client_httpx, supported_protocol_bindings=["JSONRPC"])
        client = await create_client(card, client_config=config)

        message = Message(role=Role.ROLE_USER, message_id=str(uuid.uuid4()), parts=[Part(text=json.dumps({"route_id": ROUTE_ID}))])
        request = SendMessageRequest(message=message, metadata={"skill": "evaluate-lane-capacity"})
        call_context = ClientCallContext(service_parameters={"Authorization": f"Bearer {route_decision_token}"})

        states, artifact_text = [], None
        async for event in client.send_message(request, context=call_context):
            if event.HasField("task"):
                states.append(TaskState.Name(event.task.status.state))
            elif event.HasField("status_update"):
                states.append(TaskState.Name(event.status_update.status.state))
            elif event.HasField("artifact_update"):
                for part in event.artifact_update.artifact.parts:
                    if part.HasField("text"):
                        artifact_text = part.text
        await client.close()

    assert states[:3] == ["TASK_STATE_SUBMITTED", "TASK_STATE_WORKING", "TASK_STATE_COMPLETED"]
    assert artifact_text is not None
    body = json.loads(artifact_text)
    assert body["route_id"] == ROUTE_ID


@pytest.mark.asyncio
async def test_real_network_deny_executor_never_reaches_tms_mcp(lane_agent_server, trust_boundary_fixture_token):
    """agent.trust-boundary-fixture (external trust_domain) over a real
    network connection to a real running server -- denied before tms-mcp
    (itself a real, separate running process) is contacted. Proven by
    asserting on the observable outcome (no artifact, task failed) since
    this test has no visibility into the server's internals to assert a
    call never happened -- that's the network-boundary tradeoff vs.
    test_a2a_checkpoint.py's in-process monkeypatch version."""
    import json
    import uuid

    from a2a.client import A2ACardResolver, ClientConfig, create_client
    from a2a.client.client import ClientCallContext
    from a2a.types import Message, Part, Role, SendMessageRequest, TaskState

    proc, url = lane_agent_server
    async with httpx.AsyncClient() as client_httpx:
        resolver = A2ACardResolver(client_httpx, url)
        card = await resolver.get_agent_card()
        config = ClientConfig(httpx_client=client_httpx, supported_protocol_bindings=["JSONRPC"])
        client = await create_client(card, client_config=config)

        message = Message(role=Role.ROLE_USER, message_id=str(uuid.uuid4()), parts=[Part(text=json.dumps({"route_id": ROUTE_ID}))])
        request = SendMessageRequest(message=message, metadata={"skill": "evaluate-lane-capacity"})
        call_context = ClientCallContext(service_parameters={"Authorization": f"Bearer {trust_boundary_fixture_token}"})

        states, artifact_text = [], None
        async for event in client.send_message(request, context=call_context):
            if event.HasField("task"):
                states.append(TaskState.Name(event.task.status.state))
            elif event.HasField("status_update"):
                states.append(TaskState.Name(event.status_update.status.state))
            elif event.HasField("artifact_update"):
                for part in event.artifact_update.artifact.parts:
                    if part.HasField("text"):
                        artifact_text = part.text
        await client.close()

    assert states[-1] == "TASK_STATE_FAILED"
    assert artifact_text is None


def test_restart_behavior(lane_agent_server):
    """Server stops -> a call against its URL fails clearly -> restarted ->
    discovery works again. Proves the process/network boundary is real:
    an in-process ASGITransport test has nothing analogous to "stop" --
    the app object just exists or doesn't."""
    proc, url = lane_agent_server
    _stop_server(proc)
    assert proc.poll() is not None, "process must have actually exited before this assertion"

    try:
        r = httpx.get(f"{url}/healthz", timeout=2.0)
        pytest.fail(f"expected the stopped server's port to refuse connections, got HTTP {r.status_code}: {r.text!r}")
    except httpx.TransportError:
        pass

    port = int(url.rsplit(":", 1)[1])
    env = {**os.environ, "A2A_HOST": "127.0.0.1", "A2A_PORT": str(port)}
    # tms-mcp not required for this specific check -- restart + rediscovery
    # only, not a full capacity-check call.
    new_proc = _start_server(LANE_AGENT_DIR, "lane-evaluation-agent", env, f"{url}/healthz")
    try:
        r = httpx.get(f"{url}/.well-known/agent-card.json", timeout=5.0)
        assert r.status_code == 200
        assert "evaluate-lane-capacity" in [s["id"] for s in r.json()["skills"]]
    finally:
        _stop_server(new_proc)
