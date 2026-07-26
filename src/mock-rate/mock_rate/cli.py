"""mock-rate CLI -- serve + an HTTP-client CLI for rates. Every command
except `serve` talks to a *running* mock-rate process (see
rfq_common.http_cli's docstring / mock_tms/cli.py -- same treatment)."""

from __future__ import annotations

import os

import httpx
import typer

from rfq_common.cli import create_cli
from rfq_common.http_cli import print_response

from .auth import _expected_key

app = create_cli("mock-rate", version="0.1.0")


def _base_url(base_url: str | None) -> str:
    return base_url or os.environ.get("RATE_URL", "http://127.0.0.1:8005")


def _headers() -> dict:
    return {"X-API-Key": _expected_key()}


@app.command()
def reset(base_url: str = typer.Option(None)) -> None:
    """POST /admin/reset -- reloads the running server's rates from disk."""
    print_response(httpx.post(f"{_base_url(base_url)}/admin/reset", headers=_headers()))


@app.command()
def rates(base_url: str = typer.Option(None)) -> None:
    """GET /rates on the running server."""
    print_response(httpx.get(f"{_base_url(base_url)}/rates", headers=_headers()))


@app.command(name="get-rate")
def get_rate(route_id: str, base_url: str = typer.Option(None)) -> None:
    """GET /rates/{route_id} on the running server."""
    print_response(httpx.get(f"{_base_url(base_url)}/rates/{route_id}", headers=_headers()))


@app.command(name="get-surcharges")
def get_surcharges(route_id: str, base_url: str = typer.Option(None)) -> None:
    """GET /rates/{route_id}/surcharges on the running server."""
    print_response(httpx.get(f"{_base_url(base_url)}/rates/{route_id}/surcharges", headers=_headers()))


@app.command()
def stats(base_url: str = typer.Option(None)) -> None:
    """GET /admin/stats -- memory-pressure metadata for the running server's store."""
    print_response(httpx.get(f"{_base_url(base_url)}/admin/stats", headers=_headers()))


@app.command()
def serve(host: str = "127.0.0.1", port: int = int(os.environ.get("SERVICE_PORT", 8005))) -> None:
    """Run the REST API (Swagger UI at /docs)."""
    import uvicorn

    from .api import build_app
    uvicorn.run(build_app(), host=host, port=port)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
