from __future__ import annotations

import asyncio
import os


def _resolve_host_port() -> tuple[str, int]:
    """SERVICE_HOST/SERVICE_PORT are canonical; A2A_HOST/A2A_PORT are
    legacy-compat fallbacks, kept working but not expanded elsewhere."""
    host = os.environ.get("SERVICE_HOST", os.environ.get("A2A_HOST", "127.0.0.1"))
    port = int(os.environ.get("SERVICE_PORT", os.environ.get("A2A_PORT", "8104")))
    return host, port


def main() -> None:
    import uvicorn

    from rfq_common.descriptor import new_instance_id, run_startup_self_check
    from rfq_common.observability import configure_observability
    from rfq_common.pep.preflight import MachineIdentity

    from . import settings
    from .api import RFQ_ROOT, build_app

    oidc_issuer_url = settings.oidc_issuer_url()
    identity = MachineIdentity(
        canonical_id=settings.EXPECTED_CANONICAL_ID, kind="workload",
        client_id=settings.KEYCLOAK_CLIENT_ID, secret_name="tms-mcp-svc-client-secret",
    )
    asyncio.run(run_startup_self_check(identity, oidc_issuer_url=oidc_issuer_url, root=RFQ_ROOT))

    # Same instance_id feeds BOTH this process's spans/metrics AND its
    # /descriptor endpoint (M5.5) -- one identity, two projections.
    instance_id = new_instance_id()
    configure_observability(
        service_name="tms-mcp", canonical_id=settings.EXPECTED_CANONICAL_ID,
        instance_id=instance_id, environment=os.environ.get("DEPLOYMENT_ENVIRONMENT", "local"),
    )

    host, port = _resolve_host_port()
    uvicorn.run(build_app(instance_id=instance_id), host=host, port=port)


if __name__ == "__main__":
    main()
