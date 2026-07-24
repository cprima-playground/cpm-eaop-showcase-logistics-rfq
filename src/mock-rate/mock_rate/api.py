"""Mock Rate Service -- carrier rates per route. Matches the MCP tool names
already sketched in interfaces/mcp/tools.yaml (get_contract_rate,
get_carrier_rate, get_lane_surcharges) as REST routes for now (MCP is Phase 3).
No SSO, no frontend -- APIKEY only.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException

from rfq_common.app import create_app
from rfq_common.masterdata_client import MasterdataClient
from rfq_common.secrets import SecretsClient
from rfq_common.theme import load_theme

from .auth import require_api_key
from .store import RateStore, UnknownCarrierError, UnknownCurrencyError

RFQ_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURES_DIR = RFQ_ROOT / "systems" / "rate" / "fixtures"
INVENTORY_PATH = RFQ_ROOT / "identity" / "credentials-inventory.yaml"


def _fixtures_dir() -> Path:
    return Path(os.environ.get("RATE_FIXTURES_DIR", str(DEFAULT_FIXTURES_DIR)))


def _masterdata_client() -> MasterdataClient:
    api_key = os.environ.get("MASTERDATA_API_KEY")
    if not api_key:
        api_key = SecretsClient("dev", inventory_path=INVENTORY_PATH).get("masterdata-api-key")
    base_url = os.environ.get("MASTERDATA_URL", "http://localhost:8003")
    return MasterdataClient(base_url=base_url, api_key=api_key)


def build_app(*, fixtures_dir: Path | None = None, masterdata_client: MasterdataClient | None = None) -> FastAPI:
    store = RateStore(fixtures_dir or _fixtures_dir(), masterdata_client or _masterdata_client())

    theme_pack = None
    try:
        theme_pack = load_theme(themes_dir=RFQ_ROOT / "themes")
    except Exception:
        pass

    app = create_app("Mock Rate Service", system_id="rate", theme_pack=theme_pack)
    app.state.rate_store = store

    @app.get("/rates", dependencies=[Depends(require_api_key)])
    def list_rates() -> list[dict]:
        return [r.model_dump(mode="json") for r in store.list()]

    @app.get("/rates/{route_id}", dependencies=[Depends(require_api_key)])
    def get_rate(route_id: str) -> dict:
        rate = store.get_rate(route_id)
        if rate is None:
            raise HTTPException(status_code=404, detail=f"no rate for route {route_id!r}")
        return rate.model_dump(mode="json")

    @app.get("/rates/{route_id}/surcharges", dependencies=[Depends(require_api_key)])
    def get_surcharges(route_id: str) -> dict:
        surcharges = store.surcharges(route_id)
        if surcharges is None:
            raise HTTPException(status_code=404, detail=f"no rate for route {route_id!r}")
        return {"route_id": route_id, "surcharges": surcharges}

    @app.post("/admin/reset", dependencies=[Depends(require_api_key)])
    def reset() -> dict:
        try:
            store.reload()
        except (UnknownCarrierError, UnknownCurrencyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"status": "reset"}

    return app


# NOTE: no module-level `app = build_app()` singleton -- see mock_fx/api.py's note.
