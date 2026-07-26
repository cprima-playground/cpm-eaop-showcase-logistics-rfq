"""route-decision-agent -- M5b's A2A server. Agent Card advertises ONE
business-level skill (recommend-route). Internally invokes
lane-evaluation-agent's evaluate-lane-capacity skill (A2A, not MCP) for
capacity evidence before producing a recommendation."""

from __future__ import annotations

from pathlib import Path

import httpx
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
    create_rest_routes,
)
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from fastapi import FastAPI

from rfq_common.app import create_app
from rfq_common.descriptor import DependencyInfo, build_descriptor, new_instance_id
from rfq_common.pdp import PolicyBundle
from rfq_common.settings import ServiceSettings

from . import settings
from .executor import CHILD_SKILL_ID, SKILL_ID, RouteRecommendationExecutor

RFQ_ROOT = settings.RFQ_ROOT


def _agent_card(public_url: str) -> AgentCard:
    return AgentCard(
        name="Route Decision Agent",
        description="Recommend a route, backed by a fresh capacity check. Does not approve deviations.",
        version="0.1.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        skills=[
            AgentSkill(
                id=SKILL_ID,
                name="Recommend route",
                description="Recommend a route for an RFQ, backed by a fresh lane capacity check.",
                tags=["logistics", "routing"],
                examples=['{"route_id": "SHA-HAM-MUC"}'],
                input_modes=["application/json"],
                output_modes=["application/json"],
            )
        ],
        supported_interfaces=[
            AgentInterface(
                protocol_binding="JSONRPC",
                # protocol_version deliberately left unset -- see
                # skills/a2a-agent-card/SKILL.md for why an explicit "1.0"
                # breaks the served card's legacy `url` field.
                url=f"{public_url}/a2a/jsonrpc",
            ),
        ],
    )


async def _mint_own_token(client: httpx.AsyncClient, secret: str) -> str:
    response = await client.post(
        settings.token_endpoint(),
        data={
            "grant_type": "client_credentials",
            "client_id": settings.KEYCLOAK_CLIENT_ID,
            "client_secret": secret,
        },
    )
    response.raise_for_status()
    return response.json()["access_token"]


def build_app(
    *,
    port: int = 8205,
    root: Path | None = None,
    cedar_url: str | None = None,
    bundle: PolicyBundle | None = None,
    lane_eval_base_url: str | None = None,
    lane_eval_httpx_client: httpx.AsyncClient | None = None,
    introspection_client_secret: str | None = None,
    own_client_secret: str | None = None,
    token_http_client: httpx.AsyncClient | None = None,
    child_skill: str = CHILD_SKILL_ID,
    public_url: str | None = None,
    instance_id: str | None = None,
) -> FastAPI:
    root = root or RFQ_ROOT
    cedar_url = cedar_url or settings.cedar_url()
    bundle = bundle or PolicyBundle.from_path(root / "authorization" / "policies.cedar")
    lane_eval_base_url = lane_eval_base_url or settings.lane_evaluation_agent_url()
    lane_eval_httpx_client = lane_eval_httpx_client or httpx.AsyncClient(base_url=lane_eval_base_url, timeout=10.0)
    introspection_client_secret = introspection_client_secret or settings.client_secret()
    own_client_secret = own_client_secret or settings.client_secret()
    token_http_client = token_http_client or httpx.AsyncClient(timeout=5.0)
    public_url = public_url or ServiceSettings.from_env(default_port=port).public_url
    instance_id = instance_id or new_instance_id()

    async def outbound_token_provider() -> str:
        return await _mint_own_token(token_http_client, own_client_secret)

    executor = RouteRecommendationExecutor(
        root=root,
        cedar_url=cedar_url,
        bundle=bundle,
        introspection_endpoint=settings.introspection_endpoint(),
        introspection_client_id=settings.KEYCLOAK_CLIENT_ID,
        introspection_client_secret=introspection_client_secret,
        lane_eval_base_url=lane_eval_base_url,
        lane_eval_httpx_client=lane_eval_httpx_client,
        outbound_token_provider=outbound_token_provider,
        child_skill=child_skill,
    )

    agent_card = _agent_card(public_url)
    task_store = InMemoryTaskStore()
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=task_store,
        agent_card=agent_card,
    )

    app = create_app("Route Decision Agent (A2A)", system_id="route-decision-agent")
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(agent_card=agent_card),
        jsonrpc_routes=create_jsonrpc_routes(request_handler=request_handler, rpc_url="/a2a/jsonrpc"),
        rest_routes=create_rest_routes(request_handler=request_handler, path_prefix="/a2a/rest"),
    )

    @app.get("/descriptor")
    def descriptor() -> dict:
        return build_descriptor(
            canonical_id=settings.EXPECTED_CANONICAL_ID,
            kind="a2a-agent",
            instance_id=instance_id,
            base_url=public_url,
            protocol_type="a2a",
            protocol_version="1.0",
            capability_source="agents/catalog.yaml",
            skills=[SKILL_ID],
            dependencies=[DependencyInfo(
                canonical_id="agent.lane-evaluation", relation="a2a", endpoint=lane_eval_base_url,
            )],
        ).model_dump()

    return app
