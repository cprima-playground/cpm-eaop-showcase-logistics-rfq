"""M5.9 item 6: trace/correlation-continuity test -- one real request
through the deepest real chain (Checkpoint 4's 4-hop path) must produce
ONE connected trace, not 4 disconnected ones, and correlation_id must
appear on every span in it.

Mechanical extension of test_network_checkpoint.py's own fixture chain:
same 4 real `uv run` subprocesses, same real TCP sockets, only addition
is OTEL_EXPORTER_OTLP_ENDPOINT/DEPLOYMENT_ENVIRONMENT in each subprocess's
env (pointed at the real, already-running infra/observability stack) and
a known X-Correlation-Id header on the root call so the resulting trace
can be found in Tempo deterministically, by exact value, rather than by
guessing "the most recent trace."

Skips (module-level) if the observability stack (Tempo, :3200) isn't
running, in addition to the inherited Keycloak/cedar-agent/mock-tms
preconditions -- this test proves something ABOUT the stack, it doesn't
stand it up.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_network_checkpoint import (  # noqa: E402
    CEDAR_URL,
    KEYCLOAK_URL,
    ROUTE_ID,
    _client_credentials_token,
    _free_port,
    _start_server,
    _stop_server,
    real_directory_entities_loaded,  # noqa: F401 -- reused as a fixture
)

RFQ_ROOT = Path(__file__).resolve().parents[3]
TMS_MCP_DIR = RFQ_ROOT / "src" / "tms-mcp"
LANE_AGENT_DIR = RFQ_ROOT / "src" / "lane-evaluation-agent"
ROUTE_AGENT_DIR = RFQ_ROOT / "src" / "route-decision-agent"
COMMERCIAL_AGENT_DIR = RFQ_ROOT / "src" / "commercial-normalization-agent"

TEMPO_URL = "http://localhost:3200"
OTLP_ENDPOINT = "http://localhost:4317"

EXPECTED_SERVICE_NAMES = {
    "commercial-normalization-agent", "route-decision-agent",
    "lane-evaluation-agent", "tms-mcp",
}


def _tempo_up() -> bool:
    try:
        return httpx.get(f"{TEMPO_URL}/ready", timeout=1.0).status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def preconditions():
    from test_network_checkpoint import _cedar_up, _keycloak_up, _tms_up
    if not (_keycloak_up() and _cedar_up() and _tms_up()):
        pytest.skip("Keycloak (:8081), cedar-agent (:8280), or mock-tms (:8004) not running")
    if not _tempo_up():
        pytest.skip("Tempo (:3200) not running -- infra/observability stack must be up for this test")


@pytest.fixture(scope="module")
def tms_mcp_server(real_directory_entities_loaded):
    port = _free_port()
    env = {
        **os.environ,
        "A2A_PORT": str(port),
        "CEDAR_URL": CEDAR_URL,
        "TMS_MCP_CLIENT_SECRET": os.environ.get("TMS_MCP_CLIENT_SECRET", ""),
        "TMS_API_KEY": os.environ.get("TMS_API_KEY", ""),
        "TMS_URL": "http://127.0.0.1:8004",
        "OTEL_EXPORTER_OTLP_ENDPOINT": OTLP_ENDPOINT,
        "DEPLOYMENT_ENVIRONMENT": "test",
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
        "OTEL_EXPORTER_OTLP_ENDPOINT": OTLP_ENDPOINT,
        "DEPLOYMENT_ENVIRONMENT": "test",
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
        "OTEL_EXPORTER_OTLP_ENDPOINT": OTLP_ENDPOINT,
        "DEPLOYMENT_ENVIRONMENT": "test",
    }
    proc = _start_server(ROUTE_AGENT_DIR, "route-decision-agent", env, f"http://127.0.0.1:{port}/healthz")
    yield f"http://127.0.0.1:{port}"
    _stop_server(proc)


@pytest.fixture(scope="module")
def commercial_agent_server(route_agent_server):
    port = _free_port()
    env = {
        **os.environ,
        "A2A_PORT": str(port),
        "CEDAR_URL": CEDAR_URL,
        "ROUTE_DECISION_AGENT_URL": route_agent_server,
        "COMMERCIAL_NORM_AGENT_SECRET": os.environ.get("COMMERCIAL_NORM_AGENT_SECRET", ""),
        "OTEL_EXPORTER_OTLP_ENDPOINT": OTLP_ENDPOINT,
        "DEPLOYMENT_ENVIRONMENT": "test",
    }
    proc = _start_server(COMMERCIAL_AGENT_DIR, "commercial-normalization-agent", env, f"http://127.0.0.1:{port}/healthz")
    yield f"http://127.0.0.1:{port}"
    _stop_server(proc)


@pytest.fixture()
async def lane_eval_token_as_root_caller(preconditions):
    token = await _client_credentials_token("lane-evaluation-agent-svc", os.environ.get("LANE_EVAL_AGENT_SECRET", ""))
    if not token:
        pytest.skip("LANE_EVAL_AGENT_SECRET not set or Keycloak rejected it")
    return token


async def _send_with_known_correlation_id(url: str, bearer_token: str, correlation_id: str, payload: dict):
    from a2a.client import A2ACardResolver, ClientConfig, create_client
    from a2a.client.client import ClientCallContext
    from a2a.types import Message, Part, Role, SendMessageRequest, TaskState

    async with httpx.AsyncClient(timeout=30.0) as client_httpx:
        resolver = A2ACardResolver(client_httpx, url)
        card = await resolver.get_agent_card()
        config = ClientConfig(httpx_client=client_httpx, supported_protocol_bindings=["JSONRPC"])
        client = await create_client(card, client_config=config)

        message = Message(role=Role.ROLE_USER, message_id=str(uuid.uuid4()), parts=[Part(text=json.dumps(payload))])
        request = SendMessageRequest(message=message, metadata={"skill": "normalize-route-cost"})
        call_context = ClientCallContext(service_parameters={
            "Authorization": f"Bearer {bearer_token}",
            "X-Correlation-Id": correlation_id,
        })

        states: list[str] = []
        async for event in client.send_message(request, context=call_context):
            if event.HasField("task"):
                states.append(TaskState.Name(event.task.status.state))
            elif event.HasField("status_update"):
                states.append(TaskState.Name(event.status_update.status.state))
        await client.close()
    return states


def _find_trace_by_correlation_id(correlation_id: str, *, timeout: float = 15.0) -> dict:
    """Tempo's export pipeline is async (BatchSpanProcessor) -- poll,
    don't assume the trace is queryable the instant the HTTP response
    returns."""
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            r = httpx.get(
                f"{TEMPO_URL}/api/search",
                params={"q": f'{{ span.correlation_id = "{correlation_id}" }}'},
                timeout=5.0,
            )
            r.raise_for_status()
            traces = r.json().get("traces", [])
            if traces:
                trace_id = traces[0]["traceID"]
                full = httpx.get(f"{TEMPO_URL}/api/traces/{trace_id}", timeout=5.0)
                full.raise_for_status()
                return full.json()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(1.0)
    raise TimeoutError(f"no trace found in Tempo for correlation_id={correlation_id!r} within {timeout}s (last error: {last_error})")


@pytest.mark.asyncio
async def test_4hop_chain_produces_one_connected_trace_with_shared_correlation_id(
    commercial_agent_server, lane_eval_token_as_root_caller,
):
    correlation_id = str(uuid.uuid4())
    states = await _send_with_known_correlation_id(
        commercial_agent_server, lane_eval_token_as_root_caller, correlation_id, {"route_id": ROUTE_ID},
    )
    assert states[-1] == "TASK_STATE_COMPLETED", states

    trace = _find_trace_by_correlation_id(correlation_id)
    batches = trace.get("batches", trace.get("resourceSpans", []))
    assert batches, f"trace has no spans: {trace}"

    service_names: set[str] = set()
    trace_ids: set[str] = set()
    correlation_ids_seen: set[str] = set()
    span_count = 0

    for batch in batches:
        resource_attrs = {a["key"]: a["value"].get("stringValue") for a in batch.get("resource", {}).get("attributes", [])}
        service_name = resource_attrs.get("service.name")
        if service_name:
            service_names.add(service_name)
        for scope_spans in batch.get("scopeSpans", batch.get("instrumentationLibrarySpans", [])):
            for span in scope_spans.get("spans", []):
                span_count += 1
                trace_ids.add(span["traceId"])
                for attr in span.get("attributes", []):
                    if attr["key"] == "correlation_id":
                        correlation_ids_seen.add(attr["value"].get("stringValue"))

    assert span_count > 0
    # ONE connected trace -- every span shares the same trace_id.
    assert len(trace_ids) == 1, f"expected exactly 1 trace_id, found {trace_ids}"
    # All 4 hops present, not just the entry service.
    assert EXPECTED_SERVICE_NAMES.issubset(service_names), (
        f"missing services in trace: {EXPECTED_SERVICE_NAMES - service_names} (found: {service_names})"
    )
    # correlation_id survived every hop unchanged -- the exact value we sent,
    # nowhere regenerated.
    assert correlation_ids_seen == {correlation_id}, (
        f"correlation_id was not consistent across every span: {correlation_ids_seen}"
    )
