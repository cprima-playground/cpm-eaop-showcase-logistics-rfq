"""mock-tms CLI -- serve + an HTTP-client CLI for routes/availability. Every
command except `serve` talks to a *running* mock-tms process (see
rfq_common.http_cli's docstring for why: a CLI building its own store is a
separate process with separate memory, and can't see what a live server
actually holds)."""

from __future__ import annotations

import os

import httpx
import typer

from rfq_common.cli import create_cli
from rfq_common.http_cli import print_response

from .auth import _expected_key

app = create_cli("mock-tms", version="0.1.0")


def _base_url(base_url: str | None) -> str:
    return base_url or os.environ.get("TMS_URL", "http://127.0.0.1:8004")


def _headers() -> dict:
    return {"X-API-Key": _expected_key()}


@app.command()
def reset(base_url: str = typer.Option(None)) -> None:
    """POST /admin/reset -- reloads the running server's routes/availability from disk."""
    print_response(httpx.post(f"{_base_url(base_url)}/admin/reset", headers=_headers()))


@app.command()
def routes(base_url: str = typer.Option(None)) -> None:
    """GET /routes on the running server."""
    print_response(httpx.get(f"{_base_url(base_url)}/routes", headers=_headers()))


@app.command(name="get-route")
def get_route(route_id: str, base_url: str = typer.Option(None)) -> None:
    """GET /routes/{route_id} on the running server."""
    print_response(httpx.get(f"{_base_url(base_url)}/routes/{route_id}", headers=_headers()))


@app.command(name="feasible-lanes")
def feasible_lanes(lane: str, base_url: str = typer.Option(None)) -> None:
    """GET /feasible-lanes?lane=... on the running server."""
    print_response(httpx.get(f"{_base_url(base_url)}/feasible-lanes", headers=_headers(), params={"lane": lane}))


@app.command(name="get-availability")
def get_availability(route_id: str, base_url: str = typer.Option(None)) -> None:
    """GET /routes/{route_id}/availability on the running server."""
    print_response(httpx.get(f"{_base_url(base_url)}/routes/{route_id}/availability", headers=_headers()))


@app.command(name="set-availability")
def set_availability(
    route_id: str,
    status: str,
    reason: str = typer.Option(None),
    effective_from: str = typer.Option(None),
    expected_until: str = typer.Option(None),
    affected_leg: str = typer.Option(None),
    base_url: str = typer.Option(None),
) -> None:
    """PATCH /routes/{route_id}/availability on the running server -- a real
    operational-state mutation, live on the server other callers also see."""
    body = {
        "status": status, "reason": reason, "effective_from": effective_from,
        "expected_until": expected_until, "affected_leg": affected_leg,
    }
    print_response(httpx.patch(f"{_base_url(base_url)}/routes/{route_id}/availability", headers=_headers(), json=body))


@app.command()
def stats(base_url: str = typer.Option(None)) -> None:
    """GET /admin/stats -- memory-pressure metadata for the running server's store."""
    print_response(httpx.get(f"{_base_url(base_url)}/admin/stats", headers=_headers()))


@app.command()
def serve(host: str = "127.0.0.1", port: int = int(os.environ.get("SERVICE_PORT", 8004))) -> None:
    """Run the REST API (Swagger UI at /docs)."""
    import uvicorn

    from rfq_common.descriptor import new_instance_id
    from rfq_common.observability import configure_observability

    from .api import build_app

    configure_observability(
        service_name="mock-tms", canonical_id="system.mock-tms",
        instance_id=new_instance_id(), environment=os.environ.get("DEPLOYMENT_ENVIRONMENT", "local"),
    )
    uvicorn.run(build_app(), host=host, port=port)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
