"""mock-masterdata CLI -- list/get per domain + reset + serve, on rfq_common's
base Typer app. Lets a coding agent inspect reference data without HTTP."""

from __future__ import annotations

import json

import typer

from rfq_common.cli import create_cli

from .store import DOMAINS, MasterdataStore, fixtures_dir

app = create_cli("mock-masterdata", version="0.1.0")


@app.command()
def reset() -> None:
    """Reload all 9 masterdata domains from disk."""
    store = MasterdataStore(fixtures_dir())
    counts = {d: len(s) for d, s in store.stores.items()}
    typer.echo(f"reset: {counts}")


@app.command()
def domains() -> None:
    """List the 9 masterdata domains."""
    for d in DOMAINS:
        typer.echo(d)


@app.command(name="list")
def list_domain(domain: str) -> None:
    """List every entry in a domain (parties|locations|currencies|incoterms|
    commodities|equipment|units-of-measure|dg-classes|payment-terms)."""
    if domain not in DOMAINS:
        typer.echo(f"unknown domain {domain!r}; try 'mock-masterdata domains'", err=True)
        raise typer.Exit(code=1)
    store = MasterdataStore(fixtures_dir())
    for row in store.list(domain):
        typer.echo(row.model_dump_json())


@app.command()
def get(domain: str, code: str) -> None:
    """Print one entry by code."""
    if domain not in DOMAINS:
        typer.echo(f"unknown domain {domain!r}; try 'mock-masterdata domains'", err=True)
        raise typer.Exit(code=1)
    store = MasterdataStore(fixtures_dir())
    row = store.get(domain, code)
    if row is None:
        typer.echo(f"no {domain} entry for code {code!r}", err=True)
        raise typer.Exit(code=1)
    typer.echo(row.model_dump_json())


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8003) -> None:
    """Run the REST API (Swagger UI at /docs)."""
    import uvicorn

    from .api import app as fastapi_app
    uvicorn.run(fastapi_app, host=host, port=port)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
