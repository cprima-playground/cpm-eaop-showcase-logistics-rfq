"""M6: the first MCP server with RESOURCE/STATE-SENSITIVE authorization,
not a blanket "active internal agent" check. Real flow:

  A2A/direct caller -> qms-mcp -> fetch LIVE QuoteVersion.status from
  mock-qms -> Cedar evaluates that real fact (via additional_entities,
  never the persisted store) -> permit/deny -> mock-qms only called on
  permit.

No layer mocked: real Keycloak, real cedar-agent, real mock-qms (must
already be running on :8007) creating and pricing REAL quotes -- not
fixtures pre-seeded with a status; the state transition itself (draft ->
priced) happens live, mid-test, via mock-qms's own real endpoints, and
the SAME quote flips from permit to deny for calculate_quote_price the
moment it does.

Skips (not fails) if Keycloak, cedar-agent, or mock-qms aren't reachable.
"""

from __future__ import annotations

import os
import sys
import uuid
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
QMS_URL = "http://127.0.0.1:8007"


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


def _qms_up() -> bool:
    try:
        return httpx.get(f"{QMS_URL}/healthz", timeout=1.0).status_code == 200
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
    if not (_keycloak_up() and _cedar_up() and _qms_up()):
        pytest.skip("Keycloak (:8081), cedar-agent (:8280), or mock-qms (:8007) not running")


@pytest.fixture(scope="module")
def real_directory_entities_loaded(preconditions):
    """cedar-agent is a shared sidecar -- seed the real directory
    explicitly, same rationale as every other real-stack checkpoint file
    in this repo. Also loads the two NEW state-sensitive policies this
    milestone adds (agent-may-calculate-quote-price-when-draft,
    agent-may-evaluate-quote-variance-when-priced) fresh from the real
    policies.cedar file -- not hand-copied here."""
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
    """commercial-normalization-agent owns quote-price.calculate/
    quote-variance.evaluate/route-cost.normalize (agents/catalog.yaml) --
    a real edge, not fabricated."""
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


def _qms_api_key() -> str:
    from rfq_common.secrets import SecretsClient
    env_key = os.environ.get("QMS_API_KEY")
    if env_key:
        return env_key
    return SecretsClient("dev", inventory_path=RFQ_ROOT / "identity" / "credentials-inventory.yaml").get("qms-api-key")


def _create_draft_quote() -> dict:
    """A real, freshly-created quote on the live mock-qms -- unique
    rfq_id per call so parallel/repeated test runs never collide."""
    key = _qms_api_key()
    unique = uuid.uuid4().hex[:8]
    r = httpx.post(
        f"{QMS_URL}/quotes", headers={"X-API-Key": key},
        json={"rfq_id": f"RFQ-M6-QMSMCP-{unique}", "customer_id": "ACME", "currency": "EUR"},
        timeout=5.0,
    )
    r.raise_for_status()
    return r.json()


def _compose_for_pricing(quote_id: str, version: int) -> None:
    key = _qms_api_key()
    r1 = httpx.put(
        f"{QMS_URL}/quotes/{quote_id}/versions/{version}/route-recommendation",
        headers={"X-API-Key": key},
        json={"recommendation_id": f"REC-{quote_id}-v{version}", "selected_route_id": "SHA-HAM-MUC"},
        timeout=5.0,
    )
    r1.raise_for_status()
    r2 = httpx.put(
        f"{QMS_URL}/quotes/{quote_id}/versions/{version}/pricing-inputs",
        headers={"X-API-Key": key},
        json={
            "fx_rate_ref": "FX-20260724-CNY-EUR", "rate_refs": ["SHA-HAM-MUC"],
            "pricing_terms_ref": "PT-1", "margin_floor_ref": "standard",
        },
        timeout=5.0,
    )
    r2.raise_for_status()


@pytest.fixture()
def fresh_draft_quote(preconditions):
    """A brand new draft quote, composed and ready to price, but NOT YET
    priced -- function-scoped so each test gets its own untouched draft."""
    q = _create_draft_quote()
    _compose_for_pricing(q["quote_id"], 1)
    return q


def test_calculate_quote_price_permits_on_a_real_draft_quote(client, commercial_norm_token, fresh_draft_quote):
    """The live QuoteVersion.status ("draft") is fetched from mock-qms,
    supplied to Cedar via additional_entities, and permits -- then
    mock-qms's own POST .../price actually runs and returns a real
    computed total_cost."""
    r = client.post(
        "/tools/calculate_quote_price",
        json={"quote_id": fresh_draft_quote["quote_id"], "version": 1},
        headers={"Authorization": f"Bearer {commercial_norm_token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "priced"
    assert body["total_cost_eur_cents"] is not None
    assert body["authorized_as"] == "agent.commercial-normalization"
    assert body["executing_workload"] == "workload.qms-mcp"


def test_calculate_quote_price_denies_once_the_same_quote_is_priced(client, commercial_norm_token, fresh_draft_quote):
    """SAME quote, SAME policy -- but its live status has changed
    (priced by the permit test's own real POST .../price call, or by
    this test's own first call). Proves the decision tracks the
    resource's REAL current state, not a cached snapshot: calling twice
    in a row, the second call must deny."""
    first = client.post(
        "/tools/calculate_quote_price",
        json={"quote_id": fresh_draft_quote["quote_id"], "version": 1},
        headers={"Authorization": f"Bearer {commercial_norm_token}"},
    )
    assert first.status_code == 200, first.text

    second = client.post(
        "/tools/calculate_quote_price",
        json={"quote_id": fresh_draft_quote["quote_id"], "version": 1},
        headers={"Authorization": f"Bearer {commercial_norm_token}"},
    )
    assert second.status_code == 403, second.text
    assert second.json()["determining_policies"] == []


def test_evaluate_quote_variance_denies_on_a_still_draft_quote(client, commercial_norm_token, fresh_draft_quote):
    """Never priced -- nothing to compare a variance against -- must deny."""
    r = client.post(
        "/tools/evaluate_quote_variance",
        json={"quote_id": fresh_draft_quote["quote_id"], "version": 1},
        headers={"Authorization": f"Bearer {commercial_norm_token}"},
    )
    assert r.status_code == 403, r.text


def test_evaluate_quote_variance_permits_once_priced(client, commercial_norm_token, fresh_draft_quote):
    priced = client.post(
        "/tools/calculate_quote_price",
        json={"quote_id": fresh_draft_quote["quote_id"], "version": 1},
        headers={"Authorization": f"Bearer {commercial_norm_token}"},
    )
    assert priced.status_code == 200, priced.text

    r = client.post(
        "/tools/evaluate_quote_variance",
        json={"quote_id": fresh_draft_quote["quote_id"], "version": 1},
        headers={"Authorization": f"Bearer {commercial_norm_token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "priced"
    assert body["authorized_as"] == "agent.commercial-normalization"


def test_direct_bypass_of_mock_qms_pricing_without_workload_credential_is_rejected(preconditions, fresh_draft_quote):
    """Decision #9: calling mock-qms's REST API directly, without a
    valid workload credential, must fail -- proving Cedar enforcement
    isn't just a voluntary path a cooperating MCP server takes while the
    underlying API stays open."""
    r = httpx.post(f"{QMS_URL}/quotes/{fresh_draft_quote['quote_id']}/versions/1/price")
    assert r.status_code == 401

    r_bad_key = httpx.post(
        f"{QMS_URL}/quotes/{fresh_draft_quote['quote_id']}/versions/1/price",
        headers={"X-API-Key": "not-the-real-key"},
    )
    assert r_bad_key.status_code == 401
