"""mock-masterdata CLI -- serve + an HTTP-client CLI for the 9 reference
domains. Every command except `domains`/`serve` talks to a *running*
mock-masterdata process (see rfq_common.http_cli's docstring / mock_tms/cli.py
-- same treatment). `domains` stays local -- it's a static list (DOMAINS
keys), not server state, no HTTP round-trip needed to answer it."""

from __future__ import annotations

import os

import httpx
import typer

from rfq_common.cli import create_cli
from rfq_common.http_cli import print_response

from .auth import _expected_key
from .store import DOMAINS

app = create_cli("mock-masterdata", version="0.1.0")


def _base_url(base_url: str | None) -> str:
    return base_url or os.environ.get("MASTERDATA_URL", "http://127.0.0.1:8003")


def _headers() -> dict:
    return {"X-API-Key": _expected_key()}


@app.command()
def domains() -> None:
    """List the 9 masterdata domains (static -- no HTTP round-trip)."""
    for d in DOMAINS:
        typer.echo(d)


@app.command(name="list")
def list_domain(domain: str, base_url: str = typer.Option(None)) -> None:
    """GET /{domain} on the running server."""
    if domain not in DOMAINS:
        typer.echo(f"unknown domain {domain!r}; try 'mock-masterdata domains'", err=True)
        raise typer.Exit(code=1)
    print_response(httpx.get(f"{_base_url(base_url)}/{domain}", headers=_headers()))


@app.command()
def get(domain: str, code: str, base_url: str = typer.Option(None)) -> None:
    """GET /{domain}/{code} on the running server."""
    if domain not in DOMAINS:
        typer.echo(f"unknown domain {domain!r}; try 'mock-masterdata domains'", err=True)
        raise typer.Exit(code=1)
    print_response(httpx.get(f"{_base_url(base_url)}/{domain}/{code}", headers=_headers()))


@app.command()
def reset(base_url: str = typer.Option(None)) -> None:
    """POST /admin/reset -- reloads all 9 domains from disk on the running server."""
    print_response(httpx.post(f"{_base_url(base_url)}/admin/reset", headers=_headers()))


@app.command()
def stats(base_url: str = typer.Option(None)) -> None:
    """GET /admin/stats -- per-domain + total memory-pressure metadata."""
    print_response(httpx.get(f"{_base_url(base_url)}/admin/stats", headers=_headers()))


@app.command()
def serve(host: str = "127.0.0.1", port: int = int(os.environ.get("SERVICE_PORT", 8003))) -> None:
    """Run the REST API (Swagger UI at /docs)."""
    import uvicorn

    from .api import build_app
    uvicorn.run(build_app(), host=host, port=port)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
