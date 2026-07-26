"""mock-fx CLI -- serve + an HTTP-client CLI for exchange rates/convert. Every
command except `serve` talks to a *running* mock-fx process (see
rfq_common.http_cli's docstring / mock_tms/cli.py -- same treatment)."""

from __future__ import annotations

import os

import httpx
import typer

from rfq_common.cli import create_cli
from rfq_common.http_cli import print_response

from .auth import _expected_key

app = create_cli("mock-fx", version="0.1.0")


def _base_url(base_url: str | None) -> str:
    return base_url or os.environ.get("FX_URL", "http://127.0.0.1:8001")


def _headers() -> dict:
    return {"X-API-Key": _expected_key()}


@app.command()
def reset(base_url: str = typer.Option(None)) -> None:
    """POST /admin/reset -- reloads the running server's rates (live-anchor
    refresh if FX_LIVE_ANCHOR is on -- re-fetches ECB fresh, not just at boot)."""
    print_response(httpx.post(f"{_base_url(base_url)}/admin/reset", headers=_headers()))


@app.command(name="list-rates")
def list_rates(base_url: str = typer.Option(None)) -> None:
    """GET /exchange-rates -- the latest rate for every known pair."""
    print_response(httpx.get(f"{_base_url(base_url)}/exchange-rates", headers=_headers()))


@app.command(name="get-rate")
def get_rate(base: str, quote: str, effective_at: str = typer.Option(None, "--effective-at"), base_url: str = typer.Option(None)) -> None:
    """GET /exchange-rates/{base}/{quote} at an optional point in time (ISO 8601)."""
    params = {"effectiveAt": effective_at} if effective_at else {}
    print_response(httpx.get(f"{_base_url(base_url)}/exchange-rates/{base}/{quote}", headers=_headers(), params=params))


@app.command()
def history(base: str, quote: str, days: int = typer.Option(None), base_url: str = typer.Option(None)) -> None:
    """GET /exchange-rates/{base}/{quote}/history."""
    params = {"days": days} if days is not None else {}
    print_response(httpx.get(f"{_base_url(base_url)}/exchange-rates/{base}/{quote}/history", headers=_headers(), params=params))


@app.command()
def convert(
    amount: str, from_currency: str, to_currency: str,
    effective_at: str = typer.Option(None, "--effective-at"), base_url: str = typer.Option(None),
) -> None:
    """GET /convert -- correctly rounded per the target currency's minor_unit."""
    params = {"amount": amount, "from_currency": from_currency, "to_currency": to_currency}
    if effective_at:
        params["effectiveAt"] = effective_at
    print_response(httpx.get(f"{_base_url(base_url)}/convert", headers=_headers(), params=params))


@app.command()
def stats(base_url: str = typer.Option(None)) -> None:
    """GET /admin/stats -- memory-pressure metadata for the running server's store."""
    print_response(httpx.get(f"{_base_url(base_url)}/admin/stats", headers=_headers()))


@app.command()
def serve(host: str = "127.0.0.1", port: int = int(os.environ.get("SERVICE_PORT", 8001))) -> None:
    """Run the REST API (Swagger UI at /swagger)."""
    import uvicorn

    from .api import build_app
    uvicorn.run(build_app(), host=host, port=port)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
