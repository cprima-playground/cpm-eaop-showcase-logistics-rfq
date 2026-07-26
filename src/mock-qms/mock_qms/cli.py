"""mock-qms CLI -- serve + a real HTTP-client CLI for the Quotes/Versions
surface. Unlike mock-tms's cli.py (which builds its own throwaway TmsStore
per command -- separate process, separate memory, never sees what a live
server actually holds), every command here except `serve` is an HTTP call
against a *running* mock-qms process: the only way a separate process can
reach another process's in-memory state (same reasoning as ADR-010 --
consume via the API, never reconstruct the data locally)."""

from __future__ import annotations

import json
import os

import httpx
import typer

from rfq_common.cli import create_cli

from .auth import _expected_key

app = create_cli("mock-qms", version="0.1.0")


def _base_url(base_url: str | None) -> str:
    import os
    return base_url or os.environ.get("QMS_URL", "http://127.0.0.1:8007")


def _headers() -> dict:
    return {"X-API-Key": _expected_key()}


def _print(resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        typer.echo(f"error {resp.status_code}: {resp.text}", err=True)
        raise typer.Exit(code=1)
    typer.echo(json.dumps(resp.json(), indent=2))


@app.command(name="create-quote")
def create_quote(
    rfq_id: str, customer_id: str, currency: str = "EUR",
    base_url: str = typer.Option(None, help="Default: QMS_URL env or http://127.0.0.1:8007"),
) -> None:
    """POST /quotes against the running server."""
    r = httpx.post(
        f"{_base_url(base_url)}/quotes", headers=_headers(),
        json={"rfq_id": rfq_id, "customer_id": customer_id, "currency": currency},
    )
    _print(r)


@app.command(name="get-quote")
def get_quote(quote_id: str, base_url: str = typer.Option(None)) -> None:
    """GET /quotes/{quoteId} against the running server."""
    _print(httpx.get(f"{_base_url(base_url)}/quotes/{quote_id}", headers=_headers()))


@app.command(name="list-versions")
def list_versions(quote_id: str, base_url: str = typer.Option(None)) -> None:
    """GET /quotes/{quoteId}/versions against the running server."""
    _print(httpx.get(f"{_base_url(base_url)}/quotes/{quote_id}/versions", headers=_headers()))


@app.command()
def supersede(
    quote_id: str, prior_version: int, expected_latest_version: int,
    change_reason: str = typer.Option(None), copy_from_prior: bool = True,
    base_url: str = typer.Option(None),
) -> None:
    """POST /quotes/{quoteId}/versions (D17) against the running server."""
    r = httpx.post(
        f"{_base_url(base_url)}/quotes/{quote_id}/versions",
        headers={**_headers(), "Idempotency-Key": f"cli-{prior_version}-{expected_latest_version}"},
        json={
            "prior_version": prior_version, "expected_latest_version": expected_latest_version,
            "change_reason": change_reason, "copy_from_prior": copy_from_prior,
        },
    )
    _print(r)


@app.command(name="compose-route-recommendation")
def compose_route_recommendation(
    quote_id: str, version: int, recommendation_id: str, selected_route_id: str,
    base_url: str = typer.Option(None),
) -> None:
    """PUT .../route-recommendation against the running server."""
    r = httpx.put(
        f"{_base_url(base_url)}/quotes/{quote_id}/versions/{version}/route-recommendation", headers=_headers(),
        json={"recommendation_id": recommendation_id, "selected_route_id": selected_route_id},
    )
    _print(r)


@app.command(name="compose-pricing-inputs")
def compose_pricing_inputs(
    quote_id: str, version: int, fx_rate_ref: str, pricing_terms_ref: str, margin_floor_ref: str,
    rate_ref: list[str] = typer.Option([], help="Repeatable -- one per carrier rate (route_id)"),
    base_url: str = typer.Option(None),
) -> None:
    """PUT .../pricing-inputs against the running server."""
    r = httpx.put(
        f"{_base_url(base_url)}/quotes/{quote_id}/versions/{version}/pricing-inputs", headers=_headers(),
        json={
            "fx_rate_ref": fx_rate_ref, "rate_refs": rate_ref,
            "pricing_terms_ref": pricing_terms_ref, "margin_floor_ref": margin_floor_ref,
        },
    )
    _print(r)


@app.command()
def price(quote_id: str, version: int, base_url: str = typer.Option(None)) -> None:
    """POST .../price -- draft -> priced (real total_cost + honest R1-R5, see store.py)."""
    _print(httpx.post(f"{_base_url(base_url)}/quotes/{quote_id}/versions/{version}/price", headers=_headers()))


@app.command(name="submit-for-approval")
def submit_for_approval(quote_id: str, version: int, base_url: str = typer.Option(None)) -> None:
    """POST .../submit-for-approval -- priced -> approval_required."""
    _print(httpx.post(f"{_base_url(base_url)}/quotes/{quote_id}/versions/{version}/submit-for-approval", headers=_headers()))


@app.command()
def search(
    customer_id: str = typer.Option(None), rfq_id: str = typer.Option(None),
    status: str = typer.Option(None), base_url: str = typer.Option(None),
) -> None:
    """GET /quotes against the running server."""
    params = {k: v for k, v in {"customerId": customer_id, "rfqId": rfq_id, "status": status}.items() if v is not None}
    _print(httpx.get(f"{_base_url(base_url)}/quotes", headers=_headers(), params=params))


@app.command()
def timeline(quote_id: str, base_url: str = typer.Option(None)) -> None:
    """GET /quotes/{quoteId}/timeline against the running server."""
    _print(httpx.get(f"{_base_url(base_url)}/quotes/{quote_id}/timeline", headers=_headers()))


@app.command()
def stats(base_url: str = typer.Option(None)) -> None:
    """GET /admin/stats -- memory-pressure metadata for the running server's store."""
    _print(httpx.get(f"{_base_url(base_url)}/admin/stats", headers=_headers()))


@app.command()
def reset(base_url: str = typer.Option(None)) -> None:
    """POST /admin/reset -- reloads the running server back to the fixture baseline."""
    _print(httpx.post(f"{_base_url(base_url)}/admin/reset", headers=_headers()))


@app.command()
def serve(host: str = "127.0.0.1", port: int = int(os.environ.get("SERVICE_PORT", 8007))) -> None:
    """Run the REST API (Swagger UI at /swagger)."""
    import uvicorn

    from .api import build_app
    uvicorn.run(build_app(), host=host, port=port)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
