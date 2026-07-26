"""M6: approval-mcp -- the previously-missing architecture case, proved
for real:

  A2A permit (caller identity is genuinely valid, real token)
  -> MCP invocation reaches approval-mcp
  -> live business state (fetched from mock-qms, not mutated for this
     test) makes Cedar deny

No fake identity mutation, no temporary policy change -- the SAME quote
flips from permit to deny for record_recommendation the moment its real
status changes (draft -> priced), driven by mock-qms's own real pricing
endpoint mid-test.

record_recommendation's Cedar gate uses the additional_entities
mechanism qms-mcp introduced (live QuoteVersion.status, never the
persisted store). resume_route_decision's Cedar gate reuses the
pre-existing context-based route.recommend policies (D3a/D3b/D8/D9,
unchanged) -- its real state-sensitivity is a business precondition (a
decision must exist) enforced as a 409 before Cedar even runs, same
defense-in-depth split every business system in this repo already uses.

No layer mocked: real Keycloak, real cedar-agent, real mock-qms (must
already be running on :8007), creating and progressing REAL quotes.

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

from approval_mcp.api import build_app  # noqa: E402

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
    explicitly. Loads this milestone's new policy
    (agent-may-record-route-deviation-when-draft) fresh from the real
    policies.cedar file."""
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
def route_decision_token(preconditions):
    """route-decision-agent owns route.recommend + route-deviation.propose
    (agents/catalog.yaml), mcp_access: [approval-mcp] -- a real edge."""
    token = _client_credentials_token(
        "route-decision-agent-svc", os.environ.get("ROUTE_DECISION_AGENT_SECRET", ""),
    )
    if not token:
        pytest.skip("ROUTE_DECISION_AGENT_SECRET not set or Keycloak rejected it")
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
    """POST /quotes returns the first QuoteVersion (quote_id/version), not
    the Quote aggregate -- rfq_id lives on the aggregate, not the version.
    Since this helper picked rfq_id itself, just carry it along rather
    than doing a second GET /quotes/{quoteId} round trip."""
    key = _qms_api_key()
    unique = uuid.uuid4().hex[:8]
    rfq_id = f"RFQ-M6-APPROVALMCP-{unique}"
    r = httpx.post(
        f"{QMS_URL}/quotes", headers={"X-API-Key": key},
        json={"rfq_id": rfq_id, "customer_id": "ACME", "currency": "EUR"},
        timeout=5.0,
    )
    r.raise_for_status()
    version = r.json()
    return {**version, "rfq_id": rfq_id}


def _price(quote_id: str, version: int) -> dict:
    key = _qms_api_key()
    c = httpx.Client(base_url=QMS_URL, timeout=20.0)
    r1 = c.put(f"/quotes/{quote_id}/versions/{version}/route-recommendation", headers={"X-API-Key": key},
               json={"recommendation_id": f"REC-{quote_id}-v{version}", "selected_route_id": "SHA-HAM-MUC"})
    r1.raise_for_status()
    r2 = c.put(f"/quotes/{quote_id}/versions/{version}/pricing-inputs", headers={"X-API-Key": key},
               json={"fx_rate_ref": "FX-20260724-CNY-EUR", "rate_refs": ["SHA-HAM-MUC"],
                     "pricing_terms_ref": "PT-1", "margin_floor_ref": "standard"})
    r2.raise_for_status()
    r3 = c.post(f"/quotes/{quote_id}/versions/{version}/price", headers={"X-API-Key": key})
    r3.raise_for_status()
    return r3.json()


def _submit_and_decide(quote_id: str, version: int, decision: str) -> dict:
    key = _qms_api_key()
    c = httpx.Client(base_url=QMS_URL, timeout=10.0)
    r1 = c.post(f"/quotes/{quote_id}/versions/{version}/submit-for-approval", headers={"X-API-Key": key})
    r1.raise_for_status()
    r2 = c.post(f"/quotes/{quote_id}/versions/{version}/decisions", headers={"X-API-Key": key},
                json={"decision": decision, "approver": "mona.commercial", "reason": "M6 approval-mcp checkpoint"})
    r2.raise_for_status()
    return r2.json()


@pytest.fixture()
def fresh_draft_quote(preconditions):
    return _create_draft_quote()


def test_record_recommendation_permits_on_a_real_draft_quote(client, route_decision_token, fresh_draft_quote):
    r = client.post(
        "/tools/record_recommendation",
        json={
            "quote_id": fresh_draft_quote["quote_id"], "version": 1,
            "recommendation_id": f"REC-{fresh_draft_quote['quote_id']}-v1", "selected_route_id": "SHA-HAM-MUC",
        },
        headers={"Authorization": f"Bearer {route_decision_token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recommendation_id"] == f"REC-{fresh_draft_quote['quote_id']}-v1"
    assert body["authorized_as"] == "agent.route-decision"
    assert body["executing_workload"] == "workload.approval-mcp"


def test_record_recommendation_denies_once_the_same_quote_is_priced(client, route_decision_token, fresh_draft_quote):
    """THE architecture case: real A2A-permitted caller, real token, real
    MCP invocation reaching approval-mcp -- but the SAME quote's live
    state has moved past draft (priced, via mock-qms's own real pricing
    pipeline, driven mid-test, not faked), so Cedar denies. No identity
    mutation, no policy change -- the resource's real state changed."""
    quote_id = fresh_draft_quote["quote_id"]
    recommendation_id = f"REC-{quote_id}-v1"

    first = client.post(
        "/tools/record_recommendation",
        json={"quote_id": quote_id, "version": 1, "recommendation_id": recommendation_id, "selected_route_id": "SHA-HAM-MUC"},
        headers={"Authorization": f"Bearer {route_decision_token}"},
    )
    assert first.status_code == 200, first.text

    _price(quote_id, 1)  # real mock-qms pricing pipeline -- status: draft -> priced

    second = client.post(
        "/tools/record_recommendation",
        json={"quote_id": quote_id, "version": 1, "recommendation_id": recommendation_id, "selected_route_id": "SHA-HAM-MUC"},
        headers={"Authorization": f"Bearer {route_decision_token}"},
    )
    assert second.status_code == 403, second.text
    assert second.json()["determining_policies"] == []


def test_resume_route_decision_rejects_with_409_before_a_decision_exists(client, route_decision_token, fresh_draft_quote):
    """Real business-state precondition, not an authorization question --
    Cedar is never consulted (a permitted call would still 409 here)."""
    r = client.post(
        "/tools/resume_route_decision",
        json={
            "quote_id": fresh_draft_quote["quote_id"], "version": 1, "rfq_id": fresh_draft_quote["rfq_id"],
            "cost_variance_pct_x10": 0, "transit_variance_days": 0, "margin_pct_x10": 200, "non_contracted_lane": False,
        },
        headers={"Authorization": f"Bearer {route_decision_token}"},
    )
    assert r.status_code == 409, r.text


def test_resume_route_decision_permits_once_a_decision_exists(client, route_decision_token, fresh_draft_quote):
    quote_id = fresh_draft_quote["quote_id"]
    _price(quote_id, 1)
    _submit_and_decide(quote_id, 1, "approved")

    r = client.post(
        "/tools/resume_route_decision",
        json={
            "quote_id": quote_id, "version": 1, "rfq_id": fresh_draft_quote["rfq_id"],
            "cost_variance_pct_x10": 0, "transit_variance_days": 0, "margin_pct_x10": 200, "non_contracted_lane": False,
        },
        headers={"Authorization": f"Bearer {route_decision_token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision_status"] == "approved"
    assert body["resumed"] is True
    assert body["authorized_as"] == "agent.route-decision"


def test_direct_bypass_of_mock_qms_route_recommendation_without_workload_credential_is_rejected(preconditions, fresh_draft_quote):
    """Decision #9: calling mock-qms's REST API directly, without a
    valid workload credential, must fail."""
    r = httpx.put(
        f"{QMS_URL}/quotes/{fresh_draft_quote['quote_id']}/versions/1/route-recommendation",
        json={"recommendation_id": "REC-BYPASS", "selected_route_id": "SHA-HAM-MUC"},
    )
    assert r.status_code == 401

    r_bad_key = httpx.put(
        f"{QMS_URL}/quotes/{fresh_draft_quote['quote_id']}/versions/1/route-recommendation",
        headers={"X-API-Key": "not-the-real-key"},
        json={"recommendation_id": "REC-BYPASS", "selected_route_id": "SHA-HAM-MUC"},
    )
    assert r_bad_key.status_code == 401
