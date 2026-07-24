"""Mock Corporate FX Service -- realizes interfaces/api/fx-api.md /
interfaces/api/fx.openapi.yaml on top of rfq_common's base FastAPI app.

By default, live: on boot/admin-reset it fetches real ECB reference rates
(USD/GBP/JPY/CNY vs EUR) for the last 30 days (ecb_client.py) -- the baseline
carries no breakout by design; a breakout is a scenario-pack concept, never
baked into default state. Opt-out via FX_LIVE_ANCHOR=0. If the live feed is
unreachable, falls back to a manually-cached copy of the same feed
(FX_ECB_HIST_FILE), then to the committed fixtures (fixtures/fx/*.json) plus
a generated 28-day run-up (store.py/generator.py, seeded via rfq_common.clock)
-- see fx-api.md "Mock vs live". No SSO, no MCP -- APIKEY only
(systems/mock-architecture.md).

FX is also the currency-conversion authority (/convert): it holds both the rate
and, via a REAL masterdata API call (ADR-010 -- never a duplicated file), each
currency's minor_unit, so it's the one place that rounds fractional units
correctly (0 decimals for JPY, 2 for most).
"""

from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from rfq_common.app import create_app
from rfq_common.masterdata_client import MasterdataClient, MasterdataUnavailableError
from rfq_common.models import ExchangeRate
from rfq_common.secrets import SecretsClient
from rfq_common.theme import load_theme

from .auth import require_api_key
from .convert import convert_amount
from .store import FxStore, UnknownCurrencyError


class ConvertResponse(BaseModel):
    amount: str
    from_currency: str
    to_currency: str
    rate: float
    rate_ref: str | None = None
    converted_amount: str
    minor_unit: int


class ResetResponse(BaseModel):
    status: str

RFQ_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURES_DIR = RFQ_ROOT / "fixtures" / "fx"
INVENTORY_PATH = RFQ_ROOT / "identity" / "credentials-inventory.yaml"


def _fixtures_dir() -> Path:
    return Path(os.environ.get("FX_FIXTURES_DIR", str(DEFAULT_FIXTURES_DIR)))


def _masterdata_client() -> MasterdataClient:
    """The credential FX uses to call OUT to masterdata -- same env-then-Vault
    resolution as auth.py's inbound check, but a distinct concern (outbound
    caller credential, not "who may call FX")."""
    api_key = os.environ.get("MASTERDATA_API_KEY")
    if not api_key:
        api_key = SecretsClient("dev", inventory_path=INVENTORY_PATH).get("masterdata-api-key")
    base_url = os.environ.get("MASTERDATA_URL", "http://localhost:8003")
    return MasterdataClient(base_url=base_url, api_key=api_key)


def _live_anchor_enabled() -> bool:
    """Opt-out, not opt-in: the running showcase fetches real ECB reference
    rates by default. FX_LIVE_ANCHOR=0/false/no disables it (e.g. for a fully
    offline demo without an ECB cache file configured)."""
    return os.environ.get("FX_LIVE_ANCHOR", "1").strip().lower() not in ("0", "false", "no")


def build_app(*, fixtures_dir: Path | None = None, masterdata_client: MasterdataClient | None = None) -> FastAPI:
    store = FxStore(
        fixtures_dir or _fixtures_dir(),
        masterdata_client or _masterdata_client(),
        live_anchor=_live_anchor_enabled(),
        ecb_cache_file=os.environ.get("FX_ECB_HIST_FILE"),
    )

    theme_pack = None
    try:
        theme_pack = load_theme(themes_dir=RFQ_ROOT / "themes")
    except Exception:
        pass  # theme is cosmetic; never block the API on it

    app = create_app("Mock Corporate FX Service", system_id="fx", theme_pack=theme_pack)
    app.state.fx_store = store

    @app.get("/exchange-rates", dependencies=[Depends(require_api_key)], response_model=list[ExchangeRate])
    def list_exchange_rates() -> list[ExchangeRate]:
        """The latest rate for every known pair -- an overview, not a
        point-in-time lookup (list-then-detail, matches masterdata/TMS/Rate)."""
        return store.list_latest()

    @app.get(
        "/exchange-rates/{base}/{quote}", dependencies=[Depends(require_api_key)], response_model=ExchangeRate,
        summary="Authoritative FX rate for a currency pair at a point in time.",
        openapi_extra={
            "x-domain-action": "fx-rate.read",  # -> business/decisions.md D1
            "x-resource-type": "ExchangeRate",
            "x-authz-context": ["fx_age_seconds", "quote_currency"],
            "x-consults": [{
                "service": "masterdata", "endpoint": "GET /currencies/{code}",
                "purpose": "every currency in every loaded rate is validated on reload (ADR-010, fail closed if masterdata is unreachable or the code is unknown) -- not a per-request call on THIS endpoint, but the reason this endpoint can trust base/quote are real currencies at all",
            }],
        },
    )
    def get_exchange_rate(base: str, quote: str, effectiveAt: str | None = None) -> ExchangeRate:
        try:
            rate = store.get(base, quote, effective_at=effectiveAt)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"effectiveAt is not a valid ISO 8601 timestamp: {effectiveAt!r}")
        if rate is None:
            raise HTTPException(status_code=404, detail=f"no rate for {base}/{quote}")
        return rate

    @app.get("/exchange-rates/{base}/{quote}/history", dependencies=[Depends(require_api_key)], response_model=list[ExchangeRate])
    def get_exchange_rate_history(base: str, quote: str, days: int | None = None) -> list[ExchangeRate]:
        points = store.history(base, quote)
        if days is not None:
            points = points[-days:]
        return points

    @app.get("/convert", dependencies=[Depends(require_api_key)], response_model=ConvertResponse)
    def convert(amount: str, from_currency: str, to_currency: str, effectiveAt: str | None = None) -> ConvertResponse:
        try:
            amount_dec = Decimal(amount)
        except InvalidOperation:
            raise HTTPException(status_code=400, detail=f"amount is not a valid decimal: {amount!r}")

        try:
            target_minor_unit = store.minor_unit(to_currency)
        except UnknownCurrencyError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except MasterdataUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc))

        rate = store.get(from_currency, to_currency, effective_at=effectiveAt)
        inverse = False
        if rate is None:
            rate = store.get(to_currency, from_currency, effective_at=effectiveAt)
            inverse = True
        if rate is None:
            raise HTTPException(status_code=404, detail=f"no rate for {from_currency}/{to_currency}")

        effective_rate = (1 / rate.rate) if inverse else rate.rate
        converted = convert_amount(amount_dec, effective_rate, target_minor_unit=target_minor_unit)

        return ConvertResponse(
            amount=str(amount_dec),
            from_currency=from_currency,
            to_currency=to_currency,
            rate=effective_rate,
            rate_ref=rate.rate_ref,
            converted_amount=str(converted),
            minor_unit=target_minor_unit,
        )

    @app.post("/admin/reset", dependencies=[Depends(require_api_key)], response_model=ResetResponse)
    def reset() -> ResetResponse:
        """Also doubles as the live-anchor refresh trigger: reload() re-fetches
        ECB rates fresh every call (not just at boot) -- useful if the process
        has been running long enough that its ECB anchor has gone stale."""
        store.reload()
        return ResetResponse(status="reset")

    @app.get("/admin/stats", dependencies=[Depends(require_api_key)])
    def stats() -> dict:
        return store.stats()

    return app


# NOTE: no module-level `app = build_app()` singleton (unlike before FX depended
# on masterdata). build_app() now makes a real outbound call, so constructing it
# eagerly at import time would break merely importing this module (CLI commands,
# test collection) even when nothing needs the FastAPI app yet. Callers that need
# an app instance (tests, cli.py's `serve`) call build_app() explicitly.
