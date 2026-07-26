"""M8.7 step 11: the committed OpenAPI contract must match what the app
actually serves. Canonicalized comparison, NOT raw byte-for-byte (review
feedback) -- parse both, then re-serialize with stable key ordering, so
a FastAPI/Pydantic library bump's own field-ordering changes never fail
this test on their own. Semantic contract equality is what matters."""

import json
from pathlib import Path

from mission_control_api.api import build_app

CONTRACT_PATH = Path(__file__).resolve().parents[3] / "interfaces" / "api" / "mission-control-v1.openapi.json"


def _canonical(spec: dict) -> str:
    return json.dumps(spec, indent=2, sort_keys=True)


def test_committed_contract_matches_the_live_app():
    app = build_app(instance_id="contract-test", public_url="https://mission-control.rfq-showcase.localhost")
    live_spec = app.openapi()
    committed_spec = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert _canonical(live_spec) == _canonical(committed_spec), (
        "OpenAPI contract drift -- regenerate interfaces/api/mission-control-v1.openapi.json "
        "(see docs/adr/ADR-005) and commit it alongside this route change"
    )


def test_contract_has_no_write_operations():
    committed_spec = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    write_methods = {"post", "put", "patch", "delete"}
    for path, methods in committed_spec["paths"].items():
        if not path.startswith("/api/v1"):
            continue
        found = write_methods & set(methods.keys())
        assert not found, f"{path} has write method(s) {found} -- M8 is read-only"
