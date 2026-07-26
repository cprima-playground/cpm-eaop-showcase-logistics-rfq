from __future__ import annotations

import asyncio
import os


def _resolve_host_port() -> tuple[str, int]:
    """SERVICE_HOST/SERVICE_PORT are canonical; A2A_HOST/A2A_PORT are
    legacy-compat fallbacks, kept working but not expanded elsewhere."""
    host = os.environ.get("SERVICE_HOST", os.environ.get("A2A_HOST", "127.0.0.1"))
    port = int(os.environ.get("SERVICE_PORT", os.environ.get("A2A_PORT", "8105")))
    return host, port


def main() -> None:
    import uvicorn

    from rfq_common.descriptor import new_instance_id, run_startup_self_check
    from rfq_common.observability import configure_observability
    from rfq_common.pep.preflight import MachineIdentity

    from . import settings
    from .api import RFQ_ROOT, build_app

    identity = MachineIdentity(
        canonical_id=settings.EXPECTED_CANONICAL_ID, kind="workload",
        client_id=settings.KEYCLOAK_CLIENT_ID, secret_name="rate-mcp-svc-client-secret",
    )
    asyncio.run(run_startup_self_check(identity, keycloak_url=settings.keycloak_url(), root=RFQ_ROOT))

    instance_id = new_instance_id()
    configure_observability(
        service_name="rate-mcp", canonical_id=settings.EXPECTED_CANONICAL_ID,
        instance_id=instance_id, environment=os.environ.get("DEPLOYMENT_ENVIRONMENT", "local"),
    )

    host, port = _resolve_host_port()
    uvicorn.run(build_app(instance_id=instance_id), host=host, port=port)


if __name__ == "__main__":
    main()
