"""mock-fx CLI -- reset/get-rate/serve on top of rfq_common's base Typer app.
Lets a coding agent drive the backend deterministically. reset/get-rate go
through the same masterdata-backed currency validation as the API (ADR-010:
masterdata must be consumed via API -- no CLI bypass)."""

from __future__ import annotations

import typer

from rfq_common.cli import create_cli

from . import api
from .store import FxStore

app = create_cli("mock-fx", version="0.1.0")


@app.command()
def reset() -> None:
    """Reload FX fixtures from disk (the deterministic baseline)."""
    store = FxStore(api._fixtures_dir(), api._masterdata_client())
    typer.echo(f"reset: loaded {len(store._rates)} rate snapshot(s) from {api._fixtures_dir()}")


@app.command(name="get-rate")
def get_rate(base: str, quote: str, effective_at: str = typer.Option(None, "--effective-at")) -> None:
    """Print the rate for BASE/QUOTE at an optional point in time (ISO 8601)."""
    store = FxStore(api._fixtures_dir(), api._masterdata_client())
    rate = store.get(base, quote, effective_at=effective_at)
    if rate is None:
        typer.echo(f"no rate for {base}/{quote}", err=True)
        raise typer.Exit(code=1)
    typer.echo(rate.model_dump_json())


@app.command()
def convert(amount: str, from_currency: str, to_currency: str) -> None:
    """Convert AMOUNT from FROM_CURRENCY to TO_CURRENCY (correctly rounded per
    the target currency's minor_unit -- e.g. 0 decimals for JPY)."""
    from decimal import Decimal

    from .convert import convert_amount

    store = FxStore(api._fixtures_dir(), api._masterdata_client())
    target_minor_unit = store.minor_unit(to_currency)
    rate = store.get(from_currency, to_currency)
    inverse = False
    if rate is None:
        rate = store.get(to_currency, from_currency)
        inverse = True
    if rate is None:
        typer.echo(f"no rate for {from_currency}/{to_currency}", err=True)
        raise typer.Exit(code=1)
    effective_rate = (1 / rate.rate) if inverse else rate.rate
    converted = convert_amount(Decimal(amount), effective_rate, target_minor_unit=target_minor_unit)
    typer.echo(f"{converted} {to_currency}")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8001) -> None:
    """Run the REST API (Swagger UI at /swagger)."""
    import uvicorn

    uvicorn.run(api.build_app(), host=host, port=port)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
