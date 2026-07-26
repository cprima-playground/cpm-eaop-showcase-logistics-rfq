"""M5a: lane-evaluation-agent's A2A AgentExecutor. ONE skill,
evaluate-lane-capacity, backed internally by tms-mcp's check_lane_capacity
tool (MCP, a distinct boundary from the A2A call this executor is itself
answering -- see module docstring in tests/test_a2a_checkpoint.py for the
two-boundary shape).

Flow:
  receive A2A task
  -> authenticate the A2A caller (rfq_common.mcp_auth, same introspection
     pattern M6a already proved -- this server IS a resource server too)
  -> authorize the A2A edge (Cedar: principal=caller, action=agent.delegate,
     resource=agent.lane-evaluation -- reuses M3.5's existing can_call
     policy, no new action/policy)
  -> call tms-mcp AS agent.lane-evaluation itself (this agent's own
     client-credentials token -- never the caller's identity: "the lane
     agent is executing its own capability", not forwarding the caller's
     principal downstream)
  -> MCP-layer deny (if any) surfaces as its own, independent task failure
  -> produce an A2A artifact, complete the task
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import Part, Task, TaskState, TaskStatus
from opentelemetry import metrics, trace

from rfq_common.a2a_context import skill_from_metadata
from rfq_common.mcp_auth import AuthenticationError, authenticate_request, build_token_verifier
from rfq_common.pdp import PolicyBundle
from rfq_common.pdp.entities import ref
from rfq_common.pep import AuthorizationDenied, authorize_and_enforce

SKILL_ID = "evaluate-lane-capacity"
LANE_EVAL_CANONICAL_ID = "agent.lane-evaluation"

# M5.9: real instrumentation on the actual task lifecycle (not a separate
# synthesized span). Labels are `skill` only -- never task_id/root_requester
# (M5.9's hard cardinality rule); those ride as SPAN attributes instead,
# where high-cardinality provenance data belongs.
_tracer = trace.get_tracer("lane_evaluation_agent")
_meter = metrics.get_meter("lane_evaluation_agent")
_task_duration = _meter.create_histogram("a2a.task.duration", unit="s", description="A2A task execution latency")
_tasks_active = _meter.create_up_down_counter("a2a.tasks.active", description="A2A tasks currently executing")
_tasks_failed = _meter.create_counter("a2a.tasks.failed", description="A2A tasks that ended in TASK_STATE_FAILED")


class UnknownSkillError(Exception):
    pass


class LaneCapacityExecutor(AgentExecutor):
    def __init__(
        self,
        *,
        root: Path,
        cedar_url: str,
        bundle: PolicyBundle,
        introspection_endpoint: str,
        introspection_client_id: str,
        introspection_client_secret: str,
        tms_mcp_client: httpx.AsyncClient,
        outbound_token_provider,  # callable[[], Awaitable[str]] -- mints THIS agent's own token
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
        self._tms_mcp_client = tms_mcp_client
        self._outbound_token_provider = outbound_token_provider

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id or "", context.context_id or "")
        await updater.cancel()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Thin traced wrapper -- real logic lives in _execute_impl, which
        returns True/False (completed/failed) so this wrapper can record
        real span/metric outcomes without restructuring _execute_impl's
        existing early-return control flow."""
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

        # --- Boundary 1: A2A (caller -> this agent) -------------------------
        try:
            caller = authenticate_request(authorization_header, verifier=self._token_verifier, root=self._root)
        except AuthenticationError as exc:
            await updater.failed(message=updater.new_agent_message(parts=[Part(text=f"authentication failed: {exc}")]))
            return False

        skill = skill_from_metadata(context)
        if skill != SKILL_ID:
            await updater.failed(message=updater.new_agent_message(
                parts=[Part(text=f"unsupported skill {skill!r} -- this agent only supports {SKILL_ID!r}")]))
            return False

        try:
            authorize_and_enforce(
                self._cedar_url, self._bundle, caller,
                action="agent.delegate",
                resource=ref("AgentPrincipal", LANE_EVAL_CANONICAL_ID),
                context={"skill": SKILL_ID},
                root=self._root,
            )
        except AuthorizationDenied as exc:
            await updater.failed(message=updater.new_agent_message(
                parts=[Part(text=f"A2A invocation denied: {exc}")]))
            return False

        # --- payload: expects {"route_id": "..."} as the A2A message text --
        try:
            payload = json.loads(context.get_user_input())
            route_id = payload["route_id"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            await updater.failed(message=updater.new_agent_message(
                parts=[Part(text=f"invalid request payload: {exc}")]))
            return False

        # --- Boundary 2: MCP (this agent's OWN identity -> tms-mcp) --------
        # Never the caller's principal -- this agent executes its own
        # capability, per ADR-001 decision #3's already-established shape.
        outbound_token = await self._outbound_token_provider()
        try:
            response = await self._tms_mcp_client.post(
                "/tools/check_lane_capacity",
                json={"route_id": route_id},
                headers={"Authorization": f"Bearer {outbound_token}"},
            )
        except httpx.HTTPError as exc:
            await updater.failed(message=updater.new_agent_message(
                parts=[Part(text=f"tms-mcp unreachable: {exc}")]))
            return False

        if response.status_code == 403:
            # MCP-layer deny is independent of, and downstream of, the A2A
            # permit already granted above -- surfaced as its own failure.
            await updater.failed(message=updater.new_agent_message(
                parts=[Part(text=f"MCP authorization denied: {response.json()}")]))
            return False
        if response.status_code == 404:
            await updater.failed(message=updater.new_agent_message(
                parts=[Part(text=f"route {route_id!r} not found")]))
            return False
        response.raise_for_status()

        await updater.add_artifact(
            parts=[Part(text=json.dumps(response.json()))],
            name="capacity_result",
            last_chunk=True,
        )
        await updater.complete()
        return True
