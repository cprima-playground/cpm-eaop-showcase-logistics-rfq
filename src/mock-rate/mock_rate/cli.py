"""mock-rate CLI -- reset/rates/get-rate/serve on rfq_common's base Typer app."""

from __future__ import annotations

import typer

from rfq_common.cli import create_cli

from . import api
from .store import RateStore

app = create_cli("mock-rate", version="0.1.0")


@app.command()
def reset() -> None:
    """Reload rate fixtures from disk."""
    store = RateStore(api._fixtures_dir(), api._masterdata_client())
    typer.echo(f"reset: loaded {len(store.list())} rate(s)")


@app.command()
def rates() -> None:
    """List every carrier rate."""
    store = RateStore(api._fixtures_dir(), api._masterdata_client())
    for r in store.list():
        typer.echo(r.model_dump_json())


@app.command(name="get-rate")
def get_rate(route_id: str) -> None:
    """Print the carrier rate for a route."""
    store = RateStore(api._fixtures_dir(), api._masterdata_client())
    rate = store.get_rate(route_id)
    if rate is None:
        typer.echo(f"no rate for route {route_id!r}", err=True)
        raise typer.Exit(code=1)
    typer.echo(rate.model_dump_json())


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8005) -> None:
    """Run the REST API (Swagger UI at /docs)."""
    import uvicorn

    uvicorn.run(api.build_app(), host=host, port=port)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
