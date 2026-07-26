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

    identity = MachineIdentity(
        canonical_id=settings.EXPECTED_CANONICAL_ID, kind="workload",
        client_id=settings.KEYCLOAK_CLIENT_ID, secret_name="geo-api-svc-client-secret",
    )
    asyncio.run(run_startup_self_check(identity, oidc_issuer_url=settings.oidc_issuer_url(), root=RFQ_ROOT))

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
    graph = routing.load_graph()
    version = routing.routing_version()

    instance_id = new_instance_id()
    configure_observability(
        service_name="geo-api", canonical_id=settings.EXPECTED_CANONICAL_ID,
        instance_id=instance_id, environment=os.environ.get("DEPLOYMENT_ENVIRONMENT", "local"),
    )

    cache = LegGeometryCache(settings.cache_db_path())

    host, port = _resolve_host_port()
    app = build_app(instance_id=instance_id, graph=graph, cache=cache, routing_version_value=version)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
