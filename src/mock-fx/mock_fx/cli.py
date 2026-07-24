"""mock-fx CLI -- reset/get-rate/serve on top of rfq_common's base Typer app.
Lets a coding agent drive the backend deterministically, no HTTP client needed
for get-rate/reset (RUNNING.md: scenario runner reset+apply pattern)."""

from __future__ import annotations

import typer

from rfq_common.cli import create_cli

from .api import _fixtures_dir
from .store import FxStore

app = create_cli("mock-fx", version="0.1.0")


@app.command()
def reset() -> None:
    """Reload FX fixtures from disk (the deterministic baseline)."""
    store = FxStore(_fixtures_dir())
    typer.echo(f"reset: loaded {len(store._rates)} rate snapshot(s) from {_fixtures_dir()}")


@app.command(name="get-rate")
def get_rate(base: str, quote: str, effective_at: str = typer.Option(None, "--effective-at")) -> None:
    """Print the rate for BASE/QUOTE at an optional point in time (ISO 8601)."""
    store = FxStore(_fixtures_dir())
    rate = store.get(base, quote, effective_at=effective_at)
    if rate is None:
        typer.echo(f"no rate for {base}/{quote}", err=True)
        raise typer.Exit(code=1)
    typer.echo(rate.model_dump_json())


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8001) -> None:
    """Run the REST API (Swagger UI at /docs)."""
    import uvicorn

    from .api import app as fastapi_app
    uvicorn.run(fastapi_app, host=host, port=port)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
