"""Integration Checkpoint 1: agent -> rfq_common.pep -> tms-mcp -> mock-tms,
for exactly one operation (check_lane_capacity -> capacity.check), plus the
bypass-resistance test decision #9 requires. No layer mocked: real Keycloak
(client-credentials tokens + live token introspection), real cedar-agent
(isolated sidecar, :8280), real mock-tms (must already be running on :8004,
see README -- `just serve` in src/mock-tms). tms-mcp itself is exercised as
a real FastAPI app via TestClient (in-process ASGI, not a mocked handler).

Skips (not fails) if Keycloak, cedar-agent, or mock-tms aren't reachable --
same convention as test_pdp_integration.py / test_pep.py.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

RFQ_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RFQ_ROOT / "src" / "mock-tms"))
sys.path.insert(0, str(RFQ_ROOT))

from tms_mcp.api import build_app  # noqa: E402
from tms_mcp import settings  # noqa: E402

KEYCLOAK_URL = "http://localhost:8081"
CEDAR_URL = "http://localhost:8280"
TMS_URL = "http://127.0.0.1:8004"
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


def _tms_up() -> bool:
    try:
        return httpx.get(f"{TMS_URL}/healthz", timeout=1.0).status_code == 200
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
    if not (_keycloak_up() and _cedar_up() and _tms_up()):
        pytest.skip("Keycloak (:8081), cedar-agent (:8280), or mock-tms (:8004) not running")


@pytest.fixture(scope="module")
def real_directory_entities_loaded(preconditions):
    """cedar-agent is a shared sidecar across every test module in this
    repo -- whatever entities were pushed LAST (by whichever suite ran
    most recently) are what's loaded, not necessarily the real directory.
    D10's permit/deny here depends on agent.lane-evaluation's and
    agent.trust-boundary-fixture's real trust_domain values -- must not
    rely on ambient state left by an unrelated earlier test run (found
    the hard way while building M5a/M5b -- see
    src/route-decision-agent/tests/test_a2a_chain_checkpoint.py's
    equivalent fixture for the incident this pattern comes from)."""
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
    token = _client_credentials_token(
        "lane-evaluation-agent-svc", os.environ.get("LANE_EVAL_AGENT_SECRET", ""),
    )
    if not token:
        pytest.skip("LANE_EVAL_AGENT_SECRET not set or Keycloak rejected it -- see README")
    return token


@pytest.fixture(scope="module")
def trust_boundary_fixture_token(preconditions):
    """A real, validly-authenticated agent (agent.trust-boundary-fixture,
    identity/actors.yaml) whose trust_domain is "external" -- D10
    (agent-may-check-capacity, authorization/policies.cedar) requires
    trust_domain == "internal", so this must deny. NOT an ownership-based
    deny (agents/catalog.yaml's owned_actions isn't a Cedar-enforced fact
    for this action, confirmed the hard way -- see git history/PR
    discussion): this exercises a real, already-present D10 condition."""
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


def test_permit_reaches_mock_tms(client, lane_eval_token):
    """lane-evaluation-agent owns capacity.check (agents/catalog.yaml) ->
    Cedar permits (D10, agent-may-check-capacity) -> tms-mcp calls mock-tms
    with its own workload credential -> real capacity data returned."""
    r = client.post(
        "/tools/check_lane_capacity",
        json={"route_id": ROUTE_ID},
        headers={"Authorization": f"Bearer {lane_eval_token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["route_id"] == ROUTE_ID
    assert "capacity_status" in body
    assert body["authorized_as"] == "agent.lane-evaluation"
    assert body["executing_workload"] == "workload.tms-mcp"


def test_deny_before_mock_tms_is_called(client, trust_boundary_fixture_token, monkeypatch):
    """agent.trust-boundary-fixture is a VALID caller (real token, real
    introspection) but trust_domain="external" -- D10 requires "internal",
    so Cedar must deny before mock-tms is ever called. Proven concretely:
    monkeypatch the outbound httpx.Client.get to raise if invoked at all."""
    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("mock-tms must not be called for a denied request")

    # the module-level `app` fixture already built its own httpx.Client bound
    # into the closure; patch at the httpx.Client.get level instead so this
    # assertion holds regardless of closure internals.
    original_get = httpx.Client.get
    monkeypatch.setattr(httpx.Client, "get", lambda self, *a, **kw: _must_not_be_called())
    try:
        r = client.post(
            "/tools/check_lane_capacity",
            json={"route_id": ROUTE_ID},
            headers={"Authorization": f"Bearer {trust_boundary_fixture_token}"},
        )
    finally:
        monkeypatch.setattr(httpx.Client, "get", original_get)
    assert r.status_code == 403, r.text
    assert r.json()["determining_policies"] == ["agent-may-check-capacity"] or r.json()["determining_policies"] == []


def test_direct_bypass_of_mock_tms_without_workload_credential_is_rejected(preconditions):
    """Decision #9: calling mock-tms's REST API directly, without a valid
    workload credential, must fail -- proving Cedar enforcement isn't just a
    voluntary path a cooperating MCP server takes while the underlying API
    stays open to anyone."""
    r = httpx.get(f"{TMS_URL}/routes/{ROUTE_ID}/capacity")
    assert r.status_code == 401

    r_bad_key = httpx.get(f"{TMS_URL}/routes/{ROUTE_ID}/capacity", headers={"X-API-Key": "not-the-real-key"})
    assert r_bad_key.status_code == 401
