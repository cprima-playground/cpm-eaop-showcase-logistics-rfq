"""The masterdata source (ADR-010): 9 reference domains, one list+get route pair
each, generated from store.DOMAINS so adding a 10th domain needs no new route
code. APIKEY only -- no SSO, no MCP (same posture as FX)."""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException

from rfq_common.app import create_app
from rfq_common.theme import load_theme

from .auth import require_api_key
from .store import DOMAINS, MasterdataStore, fixtures_dir

RFQ_ROOT = Path(__file__).resolve().parents[3]


def build_app(*, fixtures_dir_override: Path | None = None) -> FastAPI:
    store = MasterdataStore(fixtures_dir_override or fixtures_dir())

    theme_pack = None
    try:
        theme_pack = load_theme(themes_dir=RFQ_ROOT / "themes")
    except Exception:
        pass

    app = create_app("Masterdata Source", system_id="masterdata", theme_pack=theme_pack)
    app.state.masterdata_store = store

    for domain in DOMAINS:
        def make_routes(domain_name: str):
            @app.get(f"/{domain_name}", dependencies=[Depends(require_api_key)], name=f"list_{domain_name}")
            def list_domain() -> list[dict]:
                return [row.model_dump(mode="json") for row in store.list(domain_name)]

            @app.get(f"/{domain_name}/{{code}}", dependencies=[Depends(require_api_key)], name=f"get_{domain_name}")
            def get_one(code: str) -> dict:
                row = store.get(domain_name, code)
                if row is None:
                    raise HTTPException(status_code=404, detail=f"no {domain_name} entry for code {code!r}")
                return row.model_dump(mode="json")

        make_routes(domain)

    @app.post("/admin/reset", dependencies=[Depends(require_api_key)])
    def reset() -> dict:
        store.reload()
        return {"status": "reset", "domains": list(DOMAINS)}

    return app


app = build_app()
