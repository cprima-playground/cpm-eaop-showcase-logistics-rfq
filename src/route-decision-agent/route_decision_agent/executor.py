"""M5b: route-decision-agent's A2A AgentExecutor. Second real hop:

  commercial-normalization-agent (A2A) -> route-decision-agent (A2A)
      -> lane-evaluation-agent (A2A) -> tms-mcp (MCP) -> mock-tms

ONE skill, recommend-route. At EACH boundary, the immediate caller is what
gets authenticated + authorized -- agent.commercial-normalization is never
propagated as the Cedar principal past the first hop, and this agent's own
identity (agent.route-decision) is never propagated past the second. Each
hop derives its own outbound identity from ITS OWN resolved principal, not
from caller-supplied metadata -- `root_requester`/`parent_task_id`/
`correlation_id` are provenance ONLY (carries no authorization weight,
same posture as M4a's `delegated_by`), forwarded downstream for
traceability, never trusted as an authorization fact by the receiver.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.client.client import ClientCallContext
from a2a.helpers.proto_helpers import get_message_text
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState
from opentelemetry import metrics, trace

from rfq_common.mcp_auth import AuthenticationError, authenticate_request, build_token_verifier
from rfq_common.pdp import PolicyBundle
from rfq_common.pdp.entities import ref
from rfq_common.pep import AuthorizationDenied, authorize_and_enforce

SKILL_ID = "recommend-route"
CHILD_SKILL_ID = "evaluate-lane-capacity"  # lane-evaluation-agent's real skill id
ROUTE_DECISION_CANONICAL_ID = "agent.route-decision"

# M5.9: see lane_evaluation_agent/executor.py's identical block for the
# cardinality rationale (labels: skill only; task_id/root_requester ride
# as span attributes, never metric labels).
_tracer = trace.get_tracer("route_decision_agent")
_meter = metrics.get_meter("route_decision_agent")
_task_duration = _meter.create_histogram("a2a.task.duration", unit="s", description="A2A task execution latency")
_tasks_active = _meter.create_up_down_counter("a2a.tasks.active", description="A2A tasks currently executing")
_tasks_failed = _meter.create_counter("a2a.tasks.failed", description="A2A tasks that ended in TASK_STATE_FAILED")


def _state_name(state) -> str:
    return TaskState.Name(state)


class RouteRecommendationExecutor(AgentExecutor):
    def __init__(
        self,
        *,
        root: Path,
        cedar_url: str,
        bundle: PolicyBundle,
        introspection_endpoint: str,
        introspection_client_id: str,
        introspection_client_secret: str,
        lane_eval_base_url: str,
        lane_eval_httpx_client: httpx.AsyncClient,
        outbound_token_provider,  # callable[[], Awaitable[str]] -- mints THIS agent's own token
        child_skill: str = CHILD_SKILL_ID,
    ) -> None:
        self._root = root
        self._cedar_url = cedar_url
        self._bundle = bundle
        self._introspection_endpoint = introspection_endpoint
        self._introspection_client_id = introspection_client_id
        self._introspection_client_secret = introspection_client_secret
        self._token_verifier = build_token_verifier(
            mode="introspection", oidc_issuer_url=introspection_endpoint,
            introspection_endpoint=introspection_endpoint,
            client_id=introspection_client_id, client_secret=introspection_client_secret,
        )
        self._lane_eval_base_url = lane_eval_base_url
        self._lane_eval_httpx_client = lane_eval_httpx_client
        self._outbound_token_provider = outbound_token_provider
        self._child_skill = child_skill

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id or "", context.context_id or "")
        await updater.cancel()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Thin traced wrapper -- see lane_evaluation_agent/executor.py's
        identical wrapper for the rationale (real logic in _execute_impl,
        which returns True/False so this wrapper can record real outcomes
        without restructuring _execute_impl's existing early returns)."""
        task_id, context_id = context.task_id, context.context_id
        if not task_id or not context_id:
            return

        root_requester = (context.metadata or {}).get("root_requester")
        with _tracer.start_as_current_span(f"a2a.task.{SKILL_ID}") as span:
            span.set_attribute("a2a.task_id", task_id)
            span.set_attribute("a2a.context_id", context_id)
            if root_requester:
                span.set_attribute("a2a.root_requester", str(root_requester))
            _tasks_active.add(1, {"skill": SKILL_ID})
            t0 = time.monotonic()
            try:
                completed = await self._execute_impl(context, event_queue, task_id, context_id)
            finally:
                _tasks_active.add(-1, {"skill": SKILL_ID})
                _task_duration.record(time.monotonic() - t0, {"skill": SKILL_ID})
            span.set_attribute("a2a.task.outcome", "completed" if completed else "failed")
            if not completed:
                _tasks_failed.add(1, {"skill": SKILL_ID})

    async def _execute_impl(self, context: RequestContext, event_queue: EventQueue, task_id: str, context_id: str) -> bool:
        from a2a.types import Task, TaskStatus

        await event_queue.enqueue_event(
            Task(
                id=task_id,
                context_id=context_id,
                status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
                history=[context.message] if context.message else [],
            )
        )
        updater = TaskUpdater(event_queue, task_id, context_id)
        await updater.start_work()

        headers = context.call_context.state.get("headers", {}) if context.call_context else {}
        authorization_header = headers.get("authorization")

        # --- Boundary: A2A (immediate caller -> this agent) -----------------
        try:
            caller = authenticate_request(authorization_header, verifier=self._token_verifier, root=self._root)
        except AuthenticationError as exc:
            await updater.failed(message=updater.new_agent_message(parts=[Part(text=f"authentication failed: {exc}")]))
            return False

        skill = context.metadata.get("skill") if context.metadata else None
        if skill != SKILL_ID:
            await updater.failed(message=updater.new_agent_message(
                parts=[Part(text=f"unsupported skill {skill!r} -- this agent only supports {SKILL_ID!r}")]))
            return False

        try:
            authorize_and_enforce(
                self._cedar_url, self._bundle, caller,
                action="agent.delegate",
                resource=ref("AgentPrincipal", ROUTE_DECISION_CANONICAL_ID),
                context={"skill": SKILL_ID},
                root=self._root,
            )
        except AuthorizationDenied as exc:
            await updater.failed(message=updater.new_agent_message(
                parts=[Part(text=f"A2A invocation denied: {exc}")]))
            return False

        try:
            payload = json.loads(context.get_user_input())
            route_id = payload["route_id"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            await updater.failed(message=updater.new_agent_message(
                parts=[Part(text=f"invalid request payload: {exc}")]))
            return False

        # --- Second hop: THIS agent's own identity -> lane-evaluation-agent -
        # (never the caller's -- caller.id only rides along as provenance)
        resolver = A2ACardResolver(self._lane_eval_httpx_client, self._lane_eval_base_url)
        child_card = await resolver.get_agent_card()

        outbound_token = await self._outbound_token_provider()
        child_config = ClientConfig(httpx_client=self._lane_eval_httpx_client, supported_protocol_bindings=["JSONRPC"])
        child_client = await create_client(child_card, client_config=child_config)

        child_message = Message(
            role=Role.ROLE_USER,
            message_id=str(uuid.uuid4()),
            parts=[Part(text=json.dumps({"route_id": route_id}))],
        )
        child_request = SendMessageRequest(
            message=child_message,
            metadata={
                "skill": self._child_skill,
                "root_requester": caller.id,       # provenance only, not re-verified downstream
                "parent_task_id": task_id,
                "correlation_id": context_id,
            },
        )
        call_context = ClientCallContext(service_parameters={"Authorization": f"Bearer {outbound_token}"})

        child_states: list[str] = []
        child_artifact_text: str | None = None
        child_failure_text: str | None = None
        async for event in child_client.send_message(child_request, context=call_context):
            if event.HasField("task"):
                child_states.append(_state_name(event.task.status.state))
            elif event.HasField("status_update"):
                state_name = _state_name(event.status_update.status.state)
                child_states.append(state_name)
                if state_name == "TASK_STATE_FAILED" and event.status_update.status.HasField("message"):
                    child_failure_text = get_message_text(event.status_update.status.message, delimiter=" ")
            elif event.HasField("artifact_update"):
                for part in event.artifact_update.artifact.parts:
                    if part.HasField("text"):
                        child_artifact_text = part.text
        # NOT child_client.close() -- the a2a Client wraps this executor's
        # injected, process-lifetime httpx.AsyncClient (self._lane_eval_
        # httpx_client); Client.close() calls httpx_client.aclose() on
        # whatever's wrapped, which would permanently kill the SHARED
        # client after the first request this process ever serves. Found
        # via Checkpoint 4's concurrency/multi-request network test
        # (single-request-per-process tests never exercised the reuse
        # path). The stream itself is already fully drained by the loop
        # above -- nothing here needs releasing.

        if not child_states or child_states[-1] != "TASK_STATE_COMPLETED":
            reason = child_failure_text or f"lane evaluation ended in {child_states[-1] if child_states else 'no response'}"
            await updater.failed(message=updater.new_agent_message(
                parts=[Part(text=f"route recommendation failed: {reason}")]))
            return False

        capacity_evidence = json.loads(child_artifact_text) if child_artifact_text else None
        recommendation = {
            "route_id": route_id,
            "capacity_evidence": capacity_evidence,
            "decision": "recommend",
        }
        await updater.add_artifact(
            parts=[Part(text=json.dumps(recommendation))],
            name="route_recommendation",
            last_chunk=True,
        )
        await updater.complete()
        return True
