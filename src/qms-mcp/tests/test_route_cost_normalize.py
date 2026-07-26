"""route-cost.normalize's Cedar gate is D2 (authorization/policies.cedar,
already decided, pre-existing before this milestone) -- context.
fx_age_seconds <= 900, computed HERE from mock-fx's REAL `observed_at` on
the requested pair, never supplied by the caller. `NOW` (rfq_common.clock)
is pinned per-test via monkeypatch to make the real, fixed fixture data
(observed_at fixed at seed time) either fresh or stale on demand --
matches clock.py's own documented rationale: on real wall-clock the same
fixture drifts and flips allow<->deny between demos, so tests must pin it
the same way scenario runs do (RUNNING.md), not read real UTC "now".

Skips (not fails) if Keycloak, cedar-agent, or mock-fx aren't reachable.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

RFQ_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RFQ_ROOT / "src" / "mock-qms"))
sys.path.insert(0, str(RFQ_ROOT))

from qms_mcp.api import build_app  # noqa: E402

KEYCLOAK_URL = "http://localhost:8081"
CEDAR_URL = "http://localhost:8280"
FX_URL = "http://127.0.0.1:8001"

# Real mock-fx dev fixture: CNY/EUR observed_at "2026-07-24T08:00:00Z"
# (src/mock-fx's seeded rates.yaml equivalent) -- pin NOW near it for a
# controlled age, rather than guessing the live wall-clock offset.
FRESH_NOW = "2026-07-24T08:05:00Z"   # age ~300s -- inside the 900s window
STALE_NOW = "2026-07-25T08:05:00Z"   # age ~24h -- well outside it


def _keycloak_up() -> bool:
    try:
        return httpx.get(f"{KEYCLOAK_URL}/realms/rfq", timeout=1.0).status_code == 200
    except Exception:
        return False


def _cedar_up() -> bool:
    try:
        return httpx.get(f"{CEDAR_URL}/v1/policies", timeout=1.0).status_code == 200
    except Exception:
        return False


def _fx_up() -> bool:
    try:
        return httpx.get(f"{FX_URL}/healthz", timeout=1.0).status_code == 200
    except Exception:
        return False


def _client_credentials_token(client_id: str, client_secret: str) -> str | None:
    if not client_secret:
        return None
    r = httpx.post(
        f"{KEYCLOAK_URL}/realms/rfq/protocol/openid-connect/token",
        data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
    )
    if r.status_code != 200:
        return None
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def preconditions():
    if not (_keycloak_up() and _cedar_up() and _fx_up()):
        pytest.skip("Keycloak (:8081), cedar-agent (:8280), or mock-fx (:8001) not running")


@pytest.fixture(scope="module")
def real_directory_entities_loaded(preconditions):
    import yaml
    from rfq_common.pdp import DataAdmin, PolicyAdmin, PolicyBundle, SchemaAdmin, generate_schema
    from tools.identity.gen_cedar_entities import generate_cedar_entities
    from tools.identity.validator import validate_identity

    projection = yaml.safe_load((RFQ_ROOT / "authorization" / "authz-projection.yaml").read_text(encoding="utf-8"))
    actions_doc = yaml.safe_load((RFQ_ROOT / "business" / "actions.yaml").read_text(encoding="utf-8"))
    schema = generate_schema(projection, actions_doc)
    bundle = PolicyBundle.from_path(RFQ_ROOT / "authorization" / "policies.cedar")

    model = validate_identity(
        RFQ_ROOT / "identity" / "actors.yaml",
        RFQ_ROOT / "identity" / "groups.yaml",
        RFQ_ROOT / "business" / "departments.yaml",
        RFQ_ROOT / "business" / "job-titles.yaml",
    )
    entities = generate_cedar_entities(model, RFQ_ROOT / "agents" / "catalog.yaml")

    PolicyAdmin(CEDAR_URL).put([])
    SchemaAdmin(CEDAR_URL).put(schema)
    PolicyAdmin(CEDAR_URL).put(bundle.policies())
    DataAdmin(CEDAR_URL).put(entities)


@pytest.fixture(scope="module")
def commercial_norm_token(preconditions):
    token = _client_credentials_token(
        "commercial-normalization-agent-svc", os.environ.get("COMMERCIAL_NORM_AGENT_SECRET", ""),
    )
    if not token:
        pytest.skip("COMMERCIAL_NORM_AGENT_SECRET not set or Keycloak rejected it")
    return token


@pytest.fixture(scope="module")
def app(preconditions, real_directory_entities_loaded):
    return build_app(root=RFQ_ROOT, cedar_url=CEDAR_URL)


@pytest.fixture(scope="module")
def client(app):
    return TestClient(app)


def test_normalize_route_cost_permits_when_fx_rate_is_fresh(client, commercial_norm_token, monkeypatch):
    monkeypatch.setenv("NOW", FRESH_NOW)
    r = client.post(
        "/tools/normalize_route_cost",
        json={"route_id": "SHA-HAM-MUC", "amount": "1000", "from_currency": "CNY", "to_currency": "EUR"},
        headers={"Authorization": f"Bearer {commercial_norm_token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["route_id"] == "SHA-HAM-MUC"
    assert body["fx_age_seconds"] <= 900
    assert "converted_amount" in body
    assert body["authorized_as"] == "agent.commercial-normalization"
    assert body["executing_workload"] == "workload.qms-mcp"


def test_normalize_route_cost_denies_when_fx_rate_is_stale(client, commercial_norm_token, monkeypatch):
    """D2 (pre-existing, not new this milestone) -- context.fx_age_seconds
    > 900 must deny, and mock-fx's own /convert must never be reached."""
    monkeypatch.setenv("NOW", STALE_NOW)

    def _must_not_be_called(*a, **kw):
        raise AssertionError("mock-fx /convert must not be called when D2 denies on stale FX")

    original_get = httpx.Client.get
    monkeypatch.setattr(
        httpx.Client, "get",
        lambda self, url, *a, **kw: (_must_not_be_called() if url == "/convert" else original_get(self, url, *a, **kw)),
    )
    r = client.post(
        "/tools/normalize_route_cost",
        json={"route_id": "SHA-HAM-MUC", "amount": "1000", "from_currency": "CNY", "to_currency": "EUR"},
        headers={"Authorization": f"Bearer {commercial_norm_token}"},
    )
    assert r.status_code == 403, r.text
