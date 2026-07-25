"""Ops dashboard -- read-only views over TMS/Rate/Masterdata. First frontend
+ first human-SSO login in RfQ (see build-plan.md's ops-dashboard entry):
proves the Jinja2/HTMX/Tailwind + Keycloak plumbing (ADR-006/007) in
isolation, before QMS needs the same plumbing under approval-workflow
pressure too. No writes, no domain state machine, no MCP.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from rfq_common.app import create_app
from rfq_common.identity import Principal
from rfq_common.masterdata_client import MasterdataClient
from rfq_common.secrets import SecretsClient
from rfq_common.theme import load_theme
from rfq_common.webapp import SHARED_STATIC_DIR, SHARED_TEMPLATES_DIR, install_error_handlers

from . import config
from .clients import FxClient, QmsClient, RateClient, TmsClient
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

SYSTEM_TITLE = "Ops Dashboard"
BANNER_TEXT = "SHOWCASE — dev environment, read-only ops dashboard"
NAV_LINKS = [
    ("Routes", "/"), ("Map", "/map"), ("FX", "/fx"),
    ("Masterdata", "/masterdata"), ("Status", "/status"),
]

# Mirrors mock-fx's LIVE_CURRENCIES -- every pair mock-fx holds is
# CURRENCY/EUR, so the detail page only offers a base selector; quote is a
# fixed "EUR" (no cross-currency triangulation -- mock-fx is a neutral feed
# of what it actually has, not a derived-rate calculator).
FX_BASE_CURRENCIES = ["USD", "GBP", "JPY", "CNY"]

# systems/mock-architecture.md's capability matrix -- no MCP server actually
# runs anywhere yet (interfaces/mcp/ is greenfield), so this is a static
# designation, not a live check: None means "no MCP by design" (masterdata,
# fx, ops-dashboard, keycloak, vault), a name means "assigned, still TARGET."
MCP_SERVER_BY_SERVICE = {
    "tms": "tms-mcp (TARGET)",
    "rate": "rate-mcp (TARGET)",
    "qms": "qms-mcp (TARGET)",
}


def _masterdata_client() -> MasterdataClient:
    api_key = os.environ.get("MASTERDATA_API_KEY")
    if not api_key:
        api_key = SecretsClient("dev", inventory_path=INVENTORY_PATH).get("masterdata-api-key")
    return MasterdataClient(base_url=os.environ.get("MASTERDATA_URL", "http://127.0.0.1:8003"), api_key=api_key)


def _tms_client() -> TmsClient:
    api_key = os.environ.get("TMS_API_KEY")
    if not api_key:
        api_key = SecretsClient("dev", inventory_path=INVENTORY_PATH).get("tms-api-key")
    return TmsClient(base_url=os.environ.get("TMS_URL", "http://127.0.0.1:8004"), api_key=api_key)


def _rate_client() -> RateClient:
    api_key = os.environ.get("RATE_API_KEY")
    if not api_key:
        api_key = SecretsClient("dev", inventory_path=INVENTORY_PATH).get("rate-api-key")
    return RateClient(base_url=os.environ.get("RATE_URL", "http://127.0.0.1:8005"), api_key=api_key)


def _fx_client() -> FxClient:
    api_key = os.environ.get("FX_API_KEY")
    if not api_key:
        api_key = SecretsClient("dev", inventory_path=INVENTORY_PATH).get("fx-api-key")
    return FxClient(base_url=os.environ.get("FX_URL", "http://127.0.0.1:8001"), api_key=api_key)


def _qms_client() -> QmsClient:
    api_key = os.environ.get("QMS_API_KEY")
    if not api_key:
        api_key = SecretsClient("dev", inventory_path=INVENTORY_PATH).get("qms-api-key")
    return QmsClient(base_url=os.environ.get("QMS_URL", "http://127.0.0.1:8007"), api_key=api_key)


def _check_service(name: str, base_url: str, auth_probe, *, kind: str = "api", auth_basis: str = "an authenticated call") -> dict:
    """One backend's health, loosely shaped like the IETF health-check-response
    draft (status: pass/warn/fail). Two independent checks, not one: `/healthz`
    (unauthenticated, per rfq_common.app.create_app) proves the service is UP;
    `auth_probe()` (a real authenticated call already used elsewhere in this
    app) proves OUR credential still matches -- the two fail independently
    (KNOWN-ISSUES.md #7: a running consumer's cached key going stale after a
    Vault reseed is a real, previously-unsurfaced failure mode).

    `kind` defaults to "api" (masterdata/tms/rate/fx: pure backends other
    systems consume) but is overridable. `auth_basis` is a human-readable
    description of what auth_probe actually calls -- every bubble in
    status.html gets this as its tooltip, so "up"/"ok" is never unexplained."""
    result = {
        "name": name, "kind": kind, "base_url": base_url, "frontend_url": None,
        "swagger_url": f"{base_url}/swagger", "redoc_url": f"{base_url}/redoc", "openapi_url": f"{base_url}/openapi.json",
        "status": "fail", "reachable": False, "authenticated": False,
        "reachable_basis": f"GET {base_url}/healthz", "auth_basis": auth_basis,
        "latency_ms": None, "detail": None,
    }
    t0 = time.monotonic()
    try:
        r = httpx.get(f"{base_url}/healthz", timeout=3)
    except httpx.HTTPError as exc:
        result["detail"] = f"unreachable: {exc}"
        return result
    result["latency_ms"] = round((time.monotonic() - t0) * 1000)
    result["reachable"] = r.status_code == 200
    if not result["reachable"]:
        result["detail"] = f"/healthz returned {r.status_code}"
        return result

    try:
        auth_probe()
        result["authenticated"] = True
        result["status"] = "pass"
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            result["detail"] = "401 Unauthorized -- cached API key is stale, restart this consumer (KNOWN-ISSUES.md #7)"
        else:
            result["detail"] = f"authenticated call failed: HTTP {exc.response.status_code}"
        result["status"] = "warn"
    except Exception as exc:
        result["detail"] = f"authenticated call failed: {exc}"
        result["status"] = "warn"
    return result


def _check_vault(name: str, vault_addr: str) -> dict:
    """ADR-009's Vault-dev credential store (infra/vault/) -- every mock
    system's API key is resolved from here (rfq_common.secrets), so if it's
    down every OTHER service's "authenticated" column is about to go stale
    too, not just this row. `/v1/sys/health` needs no token -- reachability
    is "responds at all"; the auth-equivalent is unsealed+initialized (a
    sealed vault answers but every real secret read still fails)."""
    result = {
        "name": name, "kind": "api", "base_url": vault_addr, "frontend_url": None,
        "swagger_url": None, "redoc_url": None, "openapi_url": None,
        "status": "fail", "reachable": False, "authenticated": False,
        "reachable_basis": f"GET {vault_addr}/v1/sys/health (any response at all, incl. Vault's non-200 status codes)",
        "auth_basis": "response body has initialized=true and sealed=false",
        "latency_ms": None, "detail": None,
    }
    t0 = time.monotonic()
    try:
        r = httpx.get(f"{vault_addr}/v1/sys/health", timeout=3)
    except httpx.HTTPError as exc:
        result["detail"] = f"unreachable: {exc}"
        return result
    result["latency_ms"] = round((time.monotonic() - t0) * 1000)
    result["reachable"] = r.status_code in (200, 429, 472, 473, 501, 503)  # Vault uses status codes as signal, not just 200
    if not result["reachable"]:
        result["detail"] = f"/v1/sys/health returned {r.status_code}"
        return result

    try:
        body = r.json()
    except ValueError:
        result["detail"] = "/v1/sys/health did not return valid JSON"
        result["status"] = "warn"
        return result

    if body.get("initialized") and not body.get("sealed"):
        result["authenticated"] = True
        result["status"] = "pass"
    else:
        result["detail"] = f"initialized={body.get('initialized')}, sealed={body.get('sealed')}"
        result["status"] = "warn"
    return result


def _check_cedar(name: str, base_url: str) -> dict:
    """The Cedar PDP (rfq_common.pdp -- this project's OWN instance, port
    8280, deliberately not cpm-eaop's unrelated cedar-agent on 8180, see
    pdp/client.py). No API key (cedar-agent has no auth of its own) --
    reachability is `GET /v1/policies` answering at all; the auth-equivalent
    is at least one policy actually loaded (a reachable-but-empty agent
    would silently deny everything, same class of false-"up" as Vault
    sealed-but-responding)."""
    result = {
        "name": name, "kind": "api", "base_url": base_url, "frontend_url": None,
        "swagger_url": f"{base_url}/swagger-ui/", "redoc_url": None, "openapi_url": f"{base_url}/v1/openapi.json",
        "status": "fail", "reachable": False, "authenticated": False,
        "reachable_basis": f"GET {base_url}/v1/policies",
        "auth_basis": "at least one policy is actually loaded (a reachable-but-empty agent silently denies everything)",
        "latency_ms": None, "detail": None,
    }
    t0 = time.monotonic()
    try:
        r = httpx.get(f"{base_url}/v1/policies", timeout=3)
    except httpx.HTTPError as exc:
        result["detail"] = f"unreachable: {exc}"
        return result
    result["latency_ms"] = round((time.monotonic() - t0) * 1000)
    result["reachable"] = r.status_code == 200
    if not result["reachable"]:
        result["detail"] = f"/v1/policies returned {r.status_code}"
        return result

    try:
        policies = r.json()
    except ValueError:
        result["detail"] = "/v1/policies did not return valid JSON"
        result["status"] = "warn"
        return result

    if policies:
        result["authenticated"] = True
        result["status"] = "pass"
    else:
        result["detail"] = "reachable but zero policies loaded -- every authorize() call will deny"
        result["status"] = "warn"
    return result


def _check_frontend(name: str, public_base_url: str, *, authenticated: bool) -> dict:
    """Is THIS frontend up -- a real HTTP GET against its own known public
    URL's /healthz, not an assumption ("if this handler is running, it must
    be up" is true but doesn't prove the public-facing URL/edge -- Caddy,
    hostname, TLS -- actually works end-to-end)."""
    result = {
        "name": name, "kind": "frontend", "base_url": public_base_url, "frontend_url": public_base_url,
        "swagger_url": f"{public_base_url}/swagger", "redoc_url": f"{public_base_url}/redoc", "openapi_url": f"{public_base_url}/openapi.json",
        "status": "fail", "reachable": False, "authenticated": authenticated,
        "reachable_basis": f"GET {public_base_url}/healthz",
        "auth_basis": "a session cookie with a resolved Principal is present on this request",
        "latency_ms": None, "detail": None,
    }
    t0 = time.monotonic()
    try:
        r = httpx.get(f"{public_base_url}/healthz", timeout=3, verify=config.caddy_ssl_context())
    except httpx.HTTPError as exc:
        result["detail"] = f"unreachable: {exc}"
        return result
    result["latency_ms"] = round((time.monotonic() - t0) * 1000)
    result["reachable"] = r.status_code == 200
    result["status"] = "pass" if result["reachable"] else "fail"
    if not result["reachable"]:
        result["detail"] = f"/healthz returned {r.status_code}"
    return result




def _check_identity_provider(name: str, issuer_url: str) -> dict:
    """The identity server (Keycloak dev / Entra ID test-prod, TODO.md) --
    shaped like _check_service, but the two checks differ: reachability is
    the OIDC discovery document loading at all; the auth-equivalent is its
    `issuer` matching what this app is configured to trust (config.py's
    keycloak_issuer_url: a hostname mismatch here breaks every login
    silently, since Keycloak derives `iss` from whatever Host header reached
    it)."""
    result = {
        "name": name, "kind": "identity", "base_url": issuer_url, "frontend_url": issuer_url,
        "swagger_url": None, "redoc_url": None, "openapi_url": None,
        "status": "fail", "reachable": False, "authenticated": False,
        "reachable_basis": f"GET {issuer_url}/.well-known/openid-configuration",
        "auth_basis": f"the discovery doc's 'issuer' field equals the configured issuer ({issuer_url})",
        "latency_ms": None, "detail": None,
    }
    t0 = time.monotonic()
    try:
        r = httpx.get(
            f"{issuer_url}/.well-known/openid-configuration",
            timeout=3, verify=config.caddy_ssl_context(),
        )
    except httpx.HTTPError as exc:
        result["detail"] = f"unreachable: {exc}"
        return result
    result["latency_ms"] = round((time.monotonic() - t0) * 1000)
    result["reachable"] = r.status_code == 200
    if not result["reachable"]:
        result["detail"] = f"discovery doc returned {r.status_code}"
        return result

    try:
        doc_issuer = r.json().get("issuer")
    except ValueError:
        result["detail"] = "discovery doc was not valid JSON"
        result["status"] = "warn"
        return result
    if doc_issuer == issuer_url:
        result["authenticated"] = True
        result["status"] = "pass"
    else:
        result["detail"] = f"issuer mismatch: configured {issuer_url!r}, discovery doc says {doc_issuer!r}"
        result["status"] = "warn"
    return result


def _route_waypoints(route: dict, location_lookup) -> list[list[float]] | None:
    """Every leg boundary is a real waypoint (leg[i].to == leg[i+1].from) --
    used for both /map (all routes) and a route's own mini-map, so a
    multi-leg route (e.g. SHA-RTM-MUC: CNSHA->Rotterdam->Duisburg->Munich)
    bends through its real intermediate ports instead of looking direct
    (KNOWN-ISSUES.md #12/#13). Returns None if any waypoint's coordinates
    are unavailable -- never fabricate a line."""
    legs = route.get("legs") or []
    if not legs:
        return None
    codes = [legs[0]["from"]] + [leg["to"] for leg in legs]
    points = [location_lookup(code) for code in codes]
    if any(p is None for p in points):
        return None
    return [[p["lat"], p["lon"]] for p in points]


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
    qms_client: QmsClient | None = None,
) -> FastAPI:
    tms = tms_client or _tms_client()
    rate = rate_client or _rate_client()
    masterdata = masterdata_client or _masterdata_client()
    fx = fx_client or _fx_client()
    qms = qms_client or _qms_client()

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
    app.state.qms = qms
    app.add_middleware(SessionMiddleware, secret_key=config.session_secret())
    app.include_router(sso_router)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.mount("/static-shared", StaticFiles(directory=str(SHARED_STATIC_DIR)), name="static_shared")

    templates = Jinja2Templates(directory=[str(TEMPLATES_DIR), str(SHARED_TEMPLATES_DIR)])

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
            "system_title": SYSTEM_TITLE,
            "banner_text": BANNER_TEXT,
            "nav_links": NAV_LINKS,
            **extra,
        }

    install_error_handlers(app, templates, _ctx)

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

        location_cache: dict[str, dict | None] = {}

        def _location(code: str) -> dict | None:
            if code not in location_cache:
                location_cache[code] = masterdata.get("locations", code)
            return location_cache[code]

        waypoints = _route_waypoints(route, _location)
        route_json = None
        if waypoints is not None:
            route_json = json.dumps([{
                "id": route["id"],
                "lane": route["lane"],
                "status": (availability or {}).get("status", "unknown"),
                "points": waypoints,
            }])

        return templates.TemplateResponse(
            request, "route_detail.html",
            _ctx(request, route=route, availability=availability, rate=rate_info,
                 route_json=route_json, principal=principal),
        )

    @app.get("/fx", response_class=HTMLResponse)
    def fx_overview(request: Request):
        principal = _require_role(request, "ops-viewer")
        rows = []
        for r in fx.list_rates():
            base, quote = r["pair"].split("/")
            history = fx.get_rate_history(base, quote, days=30)
            rows.append({
                **r, "base": base, "quote": quote,
                "sparkline_json": json.dumps([p["rate"] for p in history]),
            })
        return templates.TemplateResponse(
            request, "fx.html",
            _ctx(request, rates=rows, principal=principal),
        )

    @app.get("/fx/{base}/{quote}", response_class=HTMLResponse)
    def fx_detail(request: Request, base: str, quote: str):
        principal = _require_role(request, "ops-viewer")
        rate = fx.get_rate(base, quote)
        history = fx.get_rate_history(base, quote, days=30)
        return templates.TemplateResponse(
            request, "fx_detail.html",
            _ctx(request, base=base, quote=quote, rate=rate,
                 base_currencies=FX_BASE_CURRENCIES,
                 history_json=json.dumps(history), principal=principal),
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
            points = _route_waypoints(r, _location)
            if points is None:
                continue  # no legs, or masterdata has no coordinates for some waypoint -- skip, don't fabricate a line
            avail = tms.get_availability(r["id"]) or {}
            map_routes.append({
                "id": r["id"],
                "lane": r["lane"],
                "status": avail.get("status", "unknown"),
                "points": points,
            })

        return templates.TemplateResponse(
            request, "map.html",
            _ctx(request, routes_json=json.dumps(map_routes), principal=principal),
        )

    @app.get("/status", response_class=HTMLResponse)
    def status_page(request: Request):
        principal = _require_role(request, "ops-viewer")
        services = [
            _check_frontend("ops-dashboard", config.public_base_url(), authenticated=principal is not None),
            _check_identity_provider("keycloak", config.keycloak_issuer_url()),
            _check_service("masterdata", masterdata.base_url, lambda: masterdata.list("currencies"),
                            auth_basis=f"GET {masterdata.base_url}/currencies with our X-API-Key"),
            _check_service("tms", tms.base_url, lambda: tms.list_routes(),
                            auth_basis=f"GET {tms.base_url}/routes with our X-API-Key"),
            _check_service("rate", rate.base_url, lambda: rate.list_rates(),
                            auth_basis=f"GET {rate.base_url}/rates with our X-API-Key"),
            _check_service("fx", fx.base_url, lambda: fx.get_rate("CNY", "EUR"),
                            auth_basis=f"GET {fx.base_url}/exchange-rates/CNY/EUR with our X-API-Key"),
            _check_service("qms", qms.base_url, lambda: qms.stats(),
                            auth_basis=f"GET {qms.base_url}/admin/stats with our X-API-Key"),
            _check_vault("vault", os.environ.get("VAULT_ADDR", "http://127.0.0.1:8200")),
            _check_cedar("policy", os.environ.get("CEDAR_AGENT_URL", "http://127.0.0.1:8280")),
        ]
        stats_clients = {"masterdata": masterdata, "tms": tms, "rate": rate, "fx": fx, "qms": qms}
        for s in services:
            s["mcp_server"] = MCP_SERVER_BY_SERVICE.get(s["name"])
            s["stats"] = None
            client = stats_clients.get(s["name"])
            if client is not None:
                # Not gated on s["authenticated"]: for qms that flag tracks
                # frontend SSO (there's no UI yet), not the X-API-Key this
                # call actually uses -- the try/except is the real safety net.
                try:
                    s["stats"] = client.stats()
                except Exception:
                    pass  # stats is metadata, not a health signal -- never fail the page over it
        overall = "pass" if all(s["status"] == "pass" for s in services) else (
            "fail" if any(s["status"] == "fail" for s in services) else "warn"
        )
        return templates.TemplateResponse(
            request, "status.html",
            _ctx(request, services=services, overall=overall, principal=principal),
        )

    return app


# NOTE: no module-level `app = build_app()` singleton -- see mock_fx/api.py's
# note. build_app() makes real outbound calls (TMS/Rate/masterdata reachability);
# constructing it eagerly at import time would break merely importing this module.
