"""Mock Corporate FX Service -- realizes interfaces/api/fx-api.md /
interfaces/api/fx.openapi.yaml on top of rfq_common's base FastAPI app.

Mocked, deterministic: rates are seeded from real historical CNY/EUR snapshots
(fixtures/fx/*.json), not a live provider (see fx-api.md "Mock vs live"). No SSO,
no MCP -- APIKEY only (systems/mock-architecture.md).
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException

from rfq_common.app import create_app
from rfq_common.theme import load_theme

from .auth import require_api_key
from .store import FxStore

RFQ_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURES_DIR = RFQ_ROOT / "fixtures" / "fx"


def _fixtures_dir() -> Path:
    return Path(os.environ.get("FX_FIXTURES_DIR", str(DEFAULT_FIXTURES_DIR)))


def build_app(*, fixtures_dir: Path | None = None) -> FastAPI:
    store = FxStore(fixtures_dir or _fixtures_dir())

    theme_pack = None
    try:
        theme_pack = load_theme(themes_dir=RFQ_ROOT / "themes")
    except Exception:
        pass  # theme is cosmetic; never block the API on it

    app = create_app("Mock Corporate FX Service", system_id="fx", theme_pack=theme_pack)
    app.state.fx_store = store

    @app.get("/exchange-rates/{base}/{quote}", dependencies=[Depends(require_api_key)])
    def get_exchange_rate(base: str, quote: str, effectiveAt: str | None = None) -> dict:
        try:
            rate = store.get(base, quote, effective_at=effectiveAt)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"effectiveAt is not a valid ISO 8601 timestamp: {effectiveAt!r}")
        if rate is None:
            raise HTTPException(status_code=404, detail=f"no rate for {base}/{quote}")
        return rate.model_dump(mode="json")

    @app.post("/admin/reset", dependencies=[Depends(require_api_key)])
    def reset() -> dict:
        store.reload()
        return {"status": "reset"}

    return app


app = build_app()
