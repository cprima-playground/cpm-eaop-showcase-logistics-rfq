"""mock-tms CLI -- reset/routes/feasible-lanes/serve on rfq_common's base Typer app."""

from __future__ import annotations

import typer

from rfq_common.cli import create_cli

from rfq_common.models import RouteAvailability

from . import api
from .store import TmsStore

app = create_cli("mock-tms", version="0.1.0")


@app.command()
def reset() -> None:
    """Reload TMS fixtures from disk."""
    store = TmsStore(api._fixtures_dir(), api._masterdata_client())
    typer.echo(f"reset: loaded {len(store.list_routes())} route(s)")


@app.command()
def routes() -> None:
    """List every route (topology)."""
    store = TmsStore(api._fixtures_dir(), api._masterdata_client())
    for r in store.list_routes():
        typer.echo(r.model_dump_json(by_alias=True))


@app.command(name="feasible-lanes")
def feasible_lanes(lane: str) -> None:
    """List routes for a lane (e.g. CNSHA-DEMUC)."""
    store = TmsStore(api._fixtures_dir(), api._masterdata_client())
    for r in store.feasible_lanes(lane):
        typer.echo(r.model_dump_json(by_alias=True))


@app.command(name="set-availability")
def set_availability(
    route_id: str,
    status: str,
    reason: str = typer.Option(None),
    effective_from: str = typer.Option(None),
    expected_until: str = typer.Option(None),
    affected_leg: str = typer.Option(None),
) -> None:
    """Set a route's live availability status (in-process demo; against a
    running server use PATCH /routes/{route_id}/availability instead)."""
    store = TmsStore(api._fixtures_dir(), api._masterdata_client())
    if store.get_route(route_id) is None:
        typer.echo(f"error: no route {route_id!r}")
        raise typer.Exit(code=1)
    avail = RouteAvailability(
        route_id=route_id,
        status=status,
        reason=reason,
        effective_from=effective_from,
        expected_until=expected_until,
        affected_leg=affected_leg,
    )
    store.set_availability(route_id, avail)
    typer.echo(avail.model_dump_json())


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8004) -> None:
    """Run the REST API (Swagger UI at /docs)."""
    import uvicorn

    uvicorn.run(api.build_app(), host=host, port=port)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
