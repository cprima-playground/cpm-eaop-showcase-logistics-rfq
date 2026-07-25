"""Mock TMS -- route topology + operational availability. Matches the MCP tool
names already sketched in interfaces/mcp/tools.yaml (get_feasible_lanes,
get_lane_transit_time, check_lane_capacity) as REST routes for now (MCP is
Phase 3). No SSO, no frontend -- APIKEY only.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException

from pydantic import BaseModel

from rfq_common.app import create_app
from rfq_common.masterdata_client import MasterdataClient
from rfq_common.models import RouteAvailability, RouteAvailabilityStatus, TransportMode
from rfq_common.secrets import SecretsClient
from rfq_common.theme import load_theme

from .auth import require_api_key
from .store import InvalidTopologyError, TmsStore, UnknownLocationError


class AvailabilityUpdate(BaseModel):
    """PATCH body for /routes/{route_id}/availability -- route_id comes from
    the path, not the body (standard REST: the resource identifies itself)."""

    status: RouteAvailabilityStatus
    reason: str | None = None
    effective_from: str | None = None
    expected_until: str | None = None
    affected_leg: str | None = None


class ResolvedRouteLeg(BaseModel):
    """API-response-only projection (never a shared domain/storage type,
    see mock_tms/api.py's own route handlers) -- a route's edges resolved
    into a denormalized leg view for consumers (ops-dashboard, tools/geo)
    that don't need to know about the edge pool."""

    origin_id: str
    destination_id: str
    mode: TransportMode
    indicative_duration_days: int

RFQ_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURES_DIR = RFQ_ROOT / "systems" / "tms" / "fixtures"
INVENTORY_PATH = RFQ_ROOT / "identity" / "credentials-inventory.yaml"


def _fixtures_dir() -> Path:
    return Path(os.environ.get("TMS_FIXTURES_DIR", str(DEFAULT_FIXTURES_DIR)))


def _masterdata_client() -> MasterdataClient:
    api_key = os.environ.get("MASTERDATA_API_KEY")
    if not api_key:
        api_key = SecretsClient("dev", inventory_path=INVENTORY_PATH).get("masterdata-api-key")
    base_url = os.environ.get("MASTERDATA_URL", "http://localhost:8003")
    return MasterdataClient(base_url=base_url, api_key=api_key)


def build_app(*, fixtures_dir: Path | None = None, masterdata_client: MasterdataClient | None = None) -> FastAPI:
    store = TmsStore(fixtures_dir or _fixtures_dir(), masterdata_client or _masterdata_client())

    theme_pack = None
    try:
        theme_pack = load_theme(themes_dir=RFQ_ROOT / "themes")
    except Exception:
        pass

    app = create_app("Mock TMS", system_id="tms", theme_pack=theme_pack)
    app.state.tms_store = store

    def _route_response(route) -> dict:
        # Coordinated migration (not backward-compatible -- see the plan's
        # own item 8): the response's `legs` array is a denormalized,
        # resolved view built by joining route.edges against the edge pool,
        # kept close to the old shape so ops-dashboard/tools-geo need only
        # a field-name update, not a structural rewrite.
        body = route.model_dump(mode="json")
        body["legs"] = [
            ResolvedRouteLeg.model_validate(leg).model_dump(mode="json") for leg in store.resolve_legs(route)
        ]
        return body

    @app.get("/routes", dependencies=[Depends(require_api_key)])
    def list_routes() -> list[dict]:
        return [_route_response(r) for r in store.list_routes()]

    @app.get("/routes/{route_id}", dependencies=[Depends(require_api_key)])
    def get_route(route_id: str) -> dict:
        route = store.get_route(route_id)
        if route is None:
            raise HTTPException(status_code=404, detail=f"no route {route_id!r}")
        return _route_response(route)

    @app.get("/edges", dependencies=[Depends(require_api_key)])
    def list_edges() -> list[dict]:
        """The raw, reusable edge pool -- groundwork for a future MCP
        route-finder to query adjacency. Direction matters: an edge never
        implies its reverse. Deterministically ordered (sorted by id)."""
        return [e.model_dump(mode="json") for e in store.list_edges()]

    @app.get("/routes/{route_id}/availability", dependencies=[Depends(require_api_key)])
    def get_availability(route_id: str) -> dict:
        avail = store.availability(route_id)
        if avail is None:
            raise HTTPException(status_code=404, detail=f"no availability for route {route_id!r}")
        return avail.model_dump(mode="json")

    @app.patch("/routes/{route_id}/availability", dependencies=[Depends(require_api_key)])
    def patch_availability(route_id: str, body: AvailabilityUpdate) -> dict:
        if store.get_route(route_id) is None:
            raise HTTPException(status_code=404, detail=f"no route {route_id!r}")
        avail = RouteAvailability(route_id=route_id, **body.model_dump())
        store.set_availability(route_id, avail)
        return avail.model_dump(mode="json")

    @app.get("/routes/{route_id}/transit-time", dependencies=[Depends(require_api_key)])
    def get_transit_time(route_id: str) -> dict:
        days = store.transit_time(route_id)
        if days is None:
            raise HTTPException(status_code=404, detail=f"no route {route_id!r}")
        return {"route_id": route_id, "transit_days": days}

    @app.get("/routes/{route_id}/capacity", dependencies=[Depends(require_api_key)])
    def get_capacity(route_id: str) -> dict:
        status = store.capacity(route_id)
        if status is None:
            raise HTTPException(status_code=404, detail=f"no availability for route {route_id!r}")
        return {"route_id": route_id, "capacity_status": status}

    @app.get("/feasible-lanes", dependencies=[Depends(require_api_key)])
    def feasible_lanes(lane: str) -> list[dict]:
        return [_route_response(r) for r in store.feasible_lanes(lane)]

    @app.post("/admin/reset", dependencies=[Depends(require_api_key)])
    def reset() -> dict:
        try:
            store.reload()
        except (UnknownLocationError, InvalidTopologyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"status": "reset"}

    @app.get("/admin/stats", dependencies=[Depends(require_api_key)])
    def stats() -> dict:
        return store.stats()

    return app


# NOTE: no module-level `app = build_app()` singleton -- see mock_fx/api.py's
# note. build_app() makes a real outbound masterdata call; constructing it
# eagerly at import time would break merely importing this module.
