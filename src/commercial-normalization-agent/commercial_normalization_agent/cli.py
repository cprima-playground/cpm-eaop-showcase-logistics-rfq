from __future__ import annotations

import asyncio
import os


def main() -> None:
    import uvicorn

    from rfq_common.descriptor import new_instance_id, run_startup_self_check
    from rfq_common.observability import configure_observability
    from rfq_common.pep.preflight import MachineIdentity

    from . import settings
    from .api import RFQ_ROOT, build_app

    identity = MachineIdentity(
        canonical_id=settings.EXPECTED_CANONICAL_ID, kind="agent",
        client_id=settings.KEYCLOAK_CLIENT_ID, secret_name="commercial-normalization-agent-client-secret",
    )
    asyncio.run(run_startup_self_check(identity, oidc_issuer_url=settings.oidc_issuer_url(), root=RFQ_ROOT))

    instance_id = new_instance_id()
    configure_observability(
        service_name="commercial-normalization-agent", canonical_id=settings.EXPECTED_CANONICAL_ID,
        instance_id=instance_id, environment=os.environ.get("DEPLOYMENT_ENVIRONMENT", "local"),
    )

    bind_host = os.environ.get("SERVICE_HOST", os.environ.get("A2A_HOST", "127.0.0.1"))
    port = int(os.environ.get("SERVICE_PORT", os.environ.get("A2A_PORT", "8206")))
    # build_app's own ServiceSettings.from_env() resolves the advertised
    # Agent Card URL (SERVICE_PUBLIC_URL, or a bind-host:port fallback) --
    # no need to duplicate that parsing here.
    uvicorn.run(build_app(port=port, instance_id=instance_id), host=bind_host, port=port)


if __name__ == "__main__":
    main()
