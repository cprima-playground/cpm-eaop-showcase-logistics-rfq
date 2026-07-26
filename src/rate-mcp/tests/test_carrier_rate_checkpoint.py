"""M6: agent -> rfq_common.pep -> rate-mcp -> mock-rate, for exactly one
operation (get_contract_rate -> carrier-rate.read), plus the bypass-
resistance test decision #9 requires. Same shape as tms-mcp's own
Integration Checkpoint 1 (M6a) -- second real MCP slice, same pattern.
No layer mocked: real Keycloak, real cedar-agent, real mock-rate (must
already be running on :8005). rate-mcp itself is exercised as a real
FastAPI app via TestClient (in-process ASGI, not a mocked handler).

Skips (not fails) if Keycloak, cedar-agent, or mock-rate aren't reachable.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

RFQ_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RFQ_ROOT / "src" / "mock-rate"))
sys.path.insert(0, str(RFQ_ROOT))

from rate_mcp.api import build_app  # noqa: E402

KEYCLOAK_URL = "http://localhost:8081"
CEDAR_URL = "http://localhost:8280"
RATE_URL = "http://127.0.0.1:8005"
ROUTE_ID = "SHA-HAM-MUC"


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


def _rate_up() -> bool:
    try:
        return httpx.get(f"{RATE_URL}/healthz", timeout=1.0).status_code == 200
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
    if not (_keycloak_up() and _cedar_up() and _rate_up()):
        pytest.skip("Keycloak (:8081), cedar-agent (:8280), or mock-rate (:8005) not running")


@pytest.fixture(scope="module")
def real_directory_entities_loaded(preconditions):
    """cedar-agent is a shared sidecar -- seed the real directory
    explicitly, same rationale as every other real-stack checkpoint file
    in this repo (see tms-mcp's identical fixture for the incident this
    pattern comes from)."""
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
def lane_eval_token(preconditions):
    """lane-evaluation-agent owns carrier-rate.read (agents/catalog.yaml,
    mcp_access includes rate-mcp) -- real edge, not fabricated."""
    token = _client_credentials_token(
        "lane-evaluation-agent-svc", os.environ.get("LANE_EVAL_AGENT_SECRET", ""),
    )
    if not token:
        pytest.skip("LANE_EVAL_AGENT_SECRET not set or Keycloak rejected it -- see README")
    return token


@pytest.fixture(scope="module")
def trust_boundary_fixture_token(preconditions):
    """agent.trust-boundary-fixture: valid caller, trust_domain=external
    -- the new agent-may-read-carrier-rate policy requires "internal",
    same condition shape as tms-mcp's D10."""
    token = _client_credentials_token(
        "trust-boundary-fixture-agent-svc", os.environ.get("TRUST_BOUNDARY_FIXTURE_SECRET", ""),
    )
    if not token:
        pytest.skip("TRUST_BOUNDARY_FIXTURE_SECRET not set or Keycloak rejected it -- see README")
    return token


@pytest.fixture(scope="module")
def app(preconditions, real_directory_entities_loaded):
    return build_app(root=RFQ_ROOT, cedar_url=CEDAR_URL)


@pytest.fixture(scope="module")
def client(app):
    return TestClient(app)


def test_permit_reaches_mock_rate(client, lane_eval_token):
    r = client.post(
        "/tools/get_contract_rate",
        json={"route_id": ROUTE_ID},
        headers={"Authorization": f"Bearer {lane_eval_token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["route_id"] == ROUTE_ID
    assert body["authorized_as"] == "agent.lane-evaluation"
    assert body["executing_workload"] == "workload.rate-mcp"


def test_deny_before_mock_rate_is_called(client, trust_boundary_fixture_token, monkeypatch):
    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("mock-rate must not be called for a denied request")

    original_get = httpx.Client.get
    monkeypatch.setattr(httpx.Client, "get", lambda self, *a, **kw: _must_not_be_called())
    try:
        r = client.post(
            "/tools/get_contract_rate",
            json={"route_id": ROUTE_ID},
            headers={"Authorization": f"Bearer {trust_boundary_fixture_token}"},
        )
    finally:
        monkeypatch.setattr(httpx.Client, "get", original_get)
    assert r.status_code == 403, r.text
    assert r.json()["determining_policies"] in ([], ["agent-may-read-carrier-rate"])


def test_direct_bypass_of_mock_rate_without_workload_credential_is_rejected(preconditions):
    """Decision #9: calling mock-rate's REST API directly, without a
    valid workload credential, must fail."""
    r = httpx.get(f"{RATE_URL}/rates/{ROUTE_ID}")
    assert r.status_code == 401

    r_bad_key = httpx.get(f"{RATE_URL}/rates/{ROUTE_ID}", headers={"X-API-Key": "not-the-real-key"})
    assert r_bad_key.status_code == 401
