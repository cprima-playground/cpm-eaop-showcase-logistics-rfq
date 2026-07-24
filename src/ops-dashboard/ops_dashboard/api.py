"""Ops dashboard -- read-only views over TMS/Rate/Masterdata. First frontend
+ first human-SSO login in RfQ (see build-plan.md's ops-dashboard entry):
proves the Jinja2/HTMX/Tailwind + Keycloak plumbing (ADR-006/007) in
isolation, before CPQ needs the same plumbing under approval-workflow
pressure too. No writes, no domain state machine, no MCP.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from rfq_common.app import create_app
from rfq_common.identity import Principal
from rfq_common.masterdata_client import MasterdataClient
from rfq_common.secrets import SecretsClient
from rfq_common.theme import load_theme

from . import config
from .clients import FxClient, RateClient, TmsClient
from .sso import router as sso_router

RFQ_ROOT = Path(__file__).resolve().parents[3]
INVENTORY_PATH = RFQ_ROOT / "identity" / "credentials-inventory.yaml"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

# Mirrors mock-masterdata's store.DOMAINS keys (ADR-010, 9 reference domains).
# Duplicated here rather than importing mock_masterdata -- the dashboard talks
# to masterdata only over its real API, never its internals.
MASTERDATA_DOMAINS = [
    "parties", "locations", "currencies", "incoterms", "commodities",
    "equipment", "units-of-measure", "dg-classes", "payment-terms",
]


def _masterdata_client() -> MasterdataClient:
    api_key = os.environ.get("MASTERDATA_API_KEY")
    if not api_key:
        api_key = SecretsClient("dev", inventory_path=INVENTORY_PATH).get("masterdata-api-key")
    return MasterdataClient(base_url=os.environ.get("MASTERDATA_URL", "http://localhost:8003"), api_key=api_key)


def _tms_client() -> TmsClient:
    api_key = os.environ.get("TMS_API_KEY")
    if not api_key:
        api_key = SecretsClient("dev", inventory_path=INVENTORY_PATH).get("tms-api-key")
    return TmsClient(base_url=os.environ.get("TMS_URL", "http://localhost:8004"), api_key=api_key)


def _rate_client() -> RateClient:
    api_key = os.environ.get("RATE_API_KEY")
    if not api_key:
        api_key = SecretsClient("dev", inventory_path=INVENTORY_PATH).get("rate-api-key")
    return RateClient(base_url=os.environ.get("RATE_URL", "http://localhost:8005"), api_key=api_key)


def _fx_client() -> FxClient:
    api_key = os.environ.get("FX_API_KEY")
    if not api_key:
        api_key = SecretsClient("dev", inventory_path=INVENTORY_PATH).get("fx-api-key")
    return FxClient(base_url=os.environ.get("FX_URL", "http://localhost:8001"), api_key=api_key)


def _current_principal(request: Request) -> Principal | None:
    raw = request.session.get("principal")
    return Principal.model_validate(raw) if raw else None


def _require_role(request: Request, role: str) -> Principal:
    """Redirect to login if anonymous; 403 if logged in but missing `role`.
    A view-level check, not a FastAPI Depends -- keeps the redirect-vs-403
    distinction explicit and simple for a two-view app."""
    principal = _current_principal(request)
    if principal is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    if not principal.has_role(role):
        raise HTTPException(status_code=403, detail=f"role {role!r} required")
    return principal


def build_app(
    *,
    tms_client: TmsClient | None = None,
    rate_client: RateClient | None = None,
    masterdata_client: MasterdataClient | None = None,
    fx_client: FxClient | None = None,
) -> FastAPI:
    tms = tms_client or _tms_client()
    rate = rate_client or _rate_client()
    masterdata = masterdata_client or _masterdata_client()
    fx = fx_client or _fx_client()

    theme_pack = None
    try:
        theme_pack = load_theme(themes_dir=RFQ_ROOT / "themes")
    except Exception:
        pass

    app = create_app("Ops Dashboard", system_id="ops-dashboard", theme_pack=theme_pack)
    app.state.tms = tms
    app.state.rate = rate
    app.state.masterdata = masterdata
    app.state.fx = fx
    app.add_middleware(SessionMiddleware, secret_key=config.session_secret())
    app.include_router(sso_router)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    @app.middleware("http")
    async def _correlation_id(request: Request, call_next):
        request.state.correlation_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Correlation-Id"] = request.state.correlation_id
        return response

    def _ctx(request: Request, **extra) -> dict:
        return {
            "request": request,
            "principal": _current_principal(request),
            "correlation_id": request.state.correlation_id,
            **extra,
        }

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        principal = _require_role(request, "ops-viewer")
        routes = tms.list_routes()
        by_status: dict[str, int] = {}
        for r in routes:
            avail = tms.get_availability(r["id"]) or {}
            status = avail.get("status", "unknown")
            by_status[status] = by_status.get(status, 0) + 1
            r["_availability_status"] = status
        return templates.TemplateResponse(
            request, "dashboard.html",
            _ctx(request, routes=routes, kpi_counts=by_status, principal=principal),
        )

    @app.get("/routes/{route_id}", response_class=HTMLResponse)
    def route_detail(request: Request, route_id: str):
        principal = _require_role(request, "ops-viewer")
        route = tms.get_route(route_id)
        if route is None:
            raise HTTPException(status_code=404, detail=f"no route {route_id!r}")
        availability = tms.get_availability(route_id)
        rate_info = rate.get_rate(route_id)
        return templates.TemplateResponse(
            request, "route_detail.html",
            _ctx(request, route=route, availability=availability, rate=rate_info, principal=principal),
        )

    @app.get("/fx", response_class=HTMLResponse)
    def fx_lookup(request: Request, base: str = "CNY", quote: str = "EUR"):
        principal = _require_role(request, "ops-viewer")
        rate = fx.get_rate(base, quote)
        return templates.TemplateResponse(
            request, "fx.html",
            _ctx(request, base=base, quote=quote, rate=rate, principal=principal),
        )

    @app.get("/masterdata", response_class=HTMLResponse)
    def masterdata_domains(request: Request):
        principal = _require_role(request, "ops-viewer")
        return templates.TemplateResponse(
            request, "masterdata.html",
            _ctx(request, domains=MASTERDATA_DOMAINS, principal=principal),
        )

    @app.get("/masterdata/{domain}", response_class=HTMLResponse)
    def masterdata_domain_detail(request: Request, domain: str):
        principal = _require_role(request, "ops-viewer")
        if domain not in MASTERDATA_DOMAINS:
            raise HTTPException(status_code=404, detail=f"no masterdata domain {domain!r}")
        rows = masterdata.list(domain)
        return templates.TemplateResponse(
            request, "masterdata_domain.html",
            _ctx(request, domain=domain, rows=rows, principal=principal),
        )

    @app.get("/map", response_class=HTMLResponse)
    def route_map(request: Request):
        principal = _require_role(request, "ops-viewer")
        routes = tms.list_routes()

        location_cache: dict[str, dict | None] = {}

        def _location(code: str) -> dict | None:
            if code not in location_cache:
                location_cache[code] = masterdata.get("locations", code)
            return location_cache[code]

        map_routes = []
        for r in routes:
            legs = r.get("legs") or []
            if not legs:
                continue
            origin = _location(legs[0]["from"])
            destination = _location(legs[-1]["to"])
            if origin is None or destination is None:
                continue  # masterdata has no coordinates for this endpoint -- skip, don't fabricate a line
            avail = tms.get_availability(r["id"]) or {}
            map_routes.append({
                "id": r["id"],
                "lane": r["lane"],
                "status": avail.get("status", "unknown"),
                # Leaflet wants [lat, lon] -- straight lines only (see KNOWN-ISSUES.md:
                # RouteLeg carries no polyline/waypoint data, only endpoints).
                "from": [origin["lat"], origin["lon"]],
                "to": [destination["lat"], destination["lon"]],
            })

        return templates.TemplateResponse(
            request, "map.html",
            _ctx(request, routes_json=json.dumps(map_routes), principal=principal),
        )

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException):
        if exc.status_code == 303:
            return RedirectResponse(exc.headers["Location"])
        return HTMLResponse(f"<h1>{exc.status_code}</h1><p>{exc.detail}</p>", status_code=exc.status_code)

    return app


# NOTE: no module-level `app = build_app()` singleton -- see mock_fx/api.py's
# note. build_app() makes real outbound calls (TMS/Rate/masterdata reachability);
# constructing it eagerly at import time would break merely importing this module.
