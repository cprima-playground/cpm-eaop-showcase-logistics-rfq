"""ops-dashboard CLI -- serve on rfq_common's base Typer app."""

from __future__ import annotations

import os

import typer

from rfq_common.cli import create_cli

from . import api

app = create_cli("ops-dashboard", version="0.1.0")


@app.command()
def serve(host: str = "127.0.0.1", port: int = int(os.environ.get("SERVICE_PORT", 8006))) -> None:
    """Run the dashboard (login at /login, Swagger UI at /docs)."""
    import uvicorn

    from rfq_common.descriptor import new_instance_id
    from rfq_common.observability import configure_observability

    # workload.ops-dashboard -- its real M10 machine identity (client_credentials
    # grant, calls geo-api), reused here as the OTel resource attribute rather
    # than inventing a parallel "system.ops-dashboard" label.
    configure_observability(
        service_name="ops-dashboard", canonical_id="workload.ops-dashboard",
        instance_id=new_instance_id(), environment=os.environ.get("DEPLOYMENT_ENVIRONMENT", "local"),
    )
    uvicorn.run(api.build_app(), host=host, port=port)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
