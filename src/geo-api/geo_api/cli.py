from __future__ import annotations

import asyncio
import os


def _resolve_host_port() -> tuple[str, int]:
    """SERVICE_HOST/SERVICE_PORT are canonical; A2A_HOST/A2A_PORT are
    legacy-compat fallbacks, same pattern every other service in this repo
    follows."""
    host = os.environ.get("SERVICE_HOST", os.environ.get("A2A_HOST", "127.0.0.1"))
    port = int(os.environ.get("SERVICE_PORT", os.environ.get("A2A_PORT", "8400")))
    return host, port


def main() -> None:
    import uvicorn

    from rfq_common.descriptor import new_instance_id, run_startup_self_check
    from rfq_common.observability import configure_observability
    from rfq_common.pep.preflight import MachineIdentity

    from . import routing, settings
    from .api import RFQ_ROOT, build_app
    from .cache import LegGeometryCache
    from .log import configure_logging, get_logger

    configure_logging()
    log = get_logger(__name__)

    log.info("startup: running identity self-check against Keycloak")
    identity = MachineIdentity(
        canonical_id=settings.EXPECTED_CANONICAL_ID, kind="workload",
        client_id=settings.KEYCLOAK_CLIENT_ID, secret_name="geo-api-svc-client-secret",
    )
    asyncio.run(run_startup_self_check(identity, oidc_issuer_url=settings.oidc_issuer_url(), root=RFQ_ROOT))
    log.info("startup: identity self-check passed")

    # D2: land-mask + register_clear_zone warm-up happens HERE, synchronously,
    # before uvicorn.run() starts serving -- not lazily on the first request.
    # landmask.register_clear_zone() has a hard load-order rule (it must run
    # for every maritime-graph node before the first blocked_geometry() call
    # or it raises) that a live server handling concurrent requests must not
    # rely on lazy first-call ordering to satisfy -- that's a race, the same
    # class of bug this session already found and fixed once in
    # ObservedServiceRegistry.refresh() (mission-control-api, commit c233f49).
    # load_graph() calls register_clear_zone() for every node as part of
    # loading, so building the graph here removes the race entirely instead
    # of adding a lock around it.
    log.info("startup: loading maritime graph and warming land-mask")
    graph = routing.load_graph()
    version = routing.routing_version()
    log.info("startup: graph loaded, %d nodes, routing_version=%s", len(graph.nodes), version)

    instance_id = new_instance_id()
    configure_observability(
        service_name="geo-api", canonical_id=settings.EXPECTED_CANONICAL_ID,
        instance_id=instance_id, environment=os.environ.get("DEPLOYMENT_ENVIRONMENT", "local"),
    )

    cache = LegGeometryCache(settings.cache_db_path())
    log.info("startup: cache opened at %s", settings.cache_db_path())

    # M10 follow-up (REVERTED, see prewarm.py's module docstring): an
    # in-process eager ocean-leg cache warm-up was tried here and pulled
    # right back out -- it reliably crashed the whole process with native
    # heap corruption ("free(): corrupted unsorted chunks" / "double free or
    # corruption (out)") within 1-2 legs, even fully sequential
    # (max_workers=1, so NOT a concurrency bug). Found live: this put
    # geo-api in a permanent crash-restart loop -- 0 ocean legs ever
    # finished caching across ~90 minutes of `restart: unless-stopped`
    # cycling, which is strictly worse than the 502-on-cold-leg behavior it
    # was meant to fix (that at least self-heals; this never serves at
    # all). Root cause not yet isolated (a single one-shot call to
    # routing.compute_leg_geometry() in a fresh process works fine, per a
    # live manual test -- the corruption appears specific to calling it
    # more than once inside one long-lived interpreter, which points at
    # shapely/pyproj/GEOS native state, not at this loop's own code).

    host, port = _resolve_host_port()
    app = build_app(instance_id=instance_id, graph=graph, cache=cache, routing_version_value=version)
    log.info("startup: serving on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
