"""geo-api -- M10's on-the-fly route-geometry compute service.

`route.geometry.compute` -> `workload.geo-api` -> REST `/v1/legs/geometry`
(D3/D4/D7): capability is stable, workload/protocol/deployment are
bindings that can change later without renaming the capability -- see
README.md's "capability vs. binding" section.

D4: OIDC AuthN via rfq_common.mcp_auth (same introspection path every other
workload uses), NO Cedar authorization decision -- this service observes no
policy, it computes a deterministic function of (from, to, mode) and caches
the result. Never calls the real authorization-decision endpoint (mechanical
guard: tests/test_no_authorization_decisions.py, same spirit as
mission-control-api's own M8.4 guard).

D5: /v1/legs/geometry's handler stays a plain `def`, not `async def` -- the
A* routing call is CPU-bound and would block the event loop if declared
async; FastAPI dispatches sync handlers to its threadpool automatically."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from rfq_common.app import create_app
from rfq_common.descriptor import build_descriptor, new_instance_id
from rfq_common.mcp_auth import AuthenticationError, authenticate_request, build_token_verifier
from rfq_common.settings import ServiceSettings

from . import routing, settings
from .cache import LegGeometryCache
from .log import get_logger
from .masterdata import LocodeNotFoundError, resolve_locode

log = get_logger(__name__)

RFQ_ROOT = settings.RFQ_ROOT

# Not a Natural Earth release version number (none is recorded anywhere this
# vendored drop came from) -- a factual description of what's actually
# bundled, for /v1/provenance's human-readable context only.
NATURAL_EARTH_LABEL = "Natural Earth 10m+50m physical land layers (data/vendor/naturalearth)"

LegMode = Literal["air", "ocean", "rail", "road"]


def build_app(
    *,
    root: Path | None = None,
    graph: routing.MaritimeGraph | None = None,
    cache: LegGeometryCache | None = None,
    masterdata_client=None,
    introspection_client_secret: str | None = None,
    public_url: str | None = None,
    instance_id: str | None = None,
    routing_version_value: str | None = None,
) -> FastAPI:
    root = root or RFQ_ROOT
    graph = graph if graph is not None else routing.load_graph()
    cache = cache or LegGeometryCache(settings.cache_db_path())
    masterdata_client = masterdata_client or settings.masterdata_client()
    introspection_client_secret = introspection_client_secret or settings.introspection_client_secret()
    token_verifier = build_token_verifier(
        mode="introspection", oidc_issuer_url=settings.oidc_issuer_url(),
        introspection_endpoint=settings.introspection_endpoint(),
        client_id=settings.KEYCLOAK_CLIENT_ID, client_secret=introspection_client_secret,
    )
    public_url = public_url or ServiceSettings.from_env(default_port=8400).public_url
    instance_id = instance_id or new_instance_id()
    version = routing_version_value or routing.routing_version()

    app = create_app("geo-api", system_id="geo")

    @app.exception_handler(AuthenticationError)
    def _auth_error(request, exc: AuthenticationError):
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    @app.get("/descriptor")
    def descriptor() -> dict:
        return build_descriptor(
            canonical_id=settings.EXPECTED_CANONICAL_ID,
            kind="platform",
            instance_id=instance_id,
            base_url=public_url,
            protocol_type="rest",
            capability_source="static:route.geometry.compute",
            skills=["route.geometry.compute"],
        ).model_dump()

    def _require_authenticated(authorization: str | None = Header(default=None)):
        """D4: authN yes, Cedar authZ no -- any authenticated principal may
        call. Raises AuthenticationError (-> 401) for a missing/invalid/
        expired token; never silently passes an unauthenticated request."""
        return authenticate_request(authorization, verifier=token_verifier, root=root)

    v1 = APIRouter(prefix="/v1")

    @v1.get("/legs/geometry")
    def legs_geometry(
        from_locode: str = Query(..., alias="from"),
        to_locode: str = Query(..., alias="to"),
        mode: LegMode = Query(...),
        _principal=Depends(_require_authenticated),
    ) -> dict:
        log.info("GET /v1/legs/geometry: %s -> %s mode=%s", from_locode, to_locode, mode)
        request_locode_cache: dict[str, tuple[float, float]] = {}
        try:
            from_coord = resolve_locode(masterdata_client, from_locode, request_locode_cache)
            to_coord = resolve_locode(masterdata_client, to_locode, request_locode_cache)
        except LocodeNotFoundError as exc:
            log.warning("GET /v1/legs/geometry: %s -> %s mode=%s: 404 %s", from_locode, to_locode, mode, exc)
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        def _compute() -> dict:
            return routing.compute_leg_geometry(
                mode=mode, from_locode=from_locode, to_locode=to_locode,
                from_coord=from_coord, to_coord=to_coord, graph=graph,
            )

        try:
            result = cache.get_or_compute(
                from_locode=from_locode, to_locode=to_locode, mode=mode, routing_version=version,
                from_coord=from_coord, to_coord=to_coord, compute=_compute,
            )
        except (routing.GraphLookupError, routing.NoMaritimePathError) as exc:
            log.warning("GET /v1/legs/geometry: %s -> %s mode=%s: 422 %s", from_locode, to_locode, mode, exc)
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception:
            log.error("GET /v1/legs/geometry: %s -> %s mode=%s: unhandled failure", from_locode, to_locode, mode, exc_info=True)
            raise

        log.info(
            "GET /v1/legs/geometry: %s -> %s mode=%s: 200 distance_km=%.1f",
            from_locode, to_locode, mode, result["distance_km"],
        )
        return {
            "from": from_locode, "to": to_locode, "mode": mode,
            "geometry": result["geometry"], "distance_km": result["distance_km"],
            "routing_version": version,
        }

    @v1.get("/provenance")
    def get_provenance() -> dict:
        """D12: the combined routing_version (the actual cache-validity
        identity) plus its components broken out for readability -- not
        file hashes of the shapefiles themselves (large, not the point)."""
        return {
            "routing_version": version,
            "routing_algorithm_version": routing.ROUTING_ALGORITHM_VERSION,
            "maritime_graph_fingerprint": _sha256_hex(routing.DEFAULT_GRAPH_PATH),
            "keepout_zones_fingerprint": _sha256_hex(routing.DEFAULT_KEEPOUT_PATH),
            "natural_earth_version": NATURAL_EARTH_LABEL,
        }

    app.include_router(v1)

    return app


def _sha256_hex(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()
