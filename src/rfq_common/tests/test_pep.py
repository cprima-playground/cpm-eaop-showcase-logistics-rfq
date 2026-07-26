"""M4a: rfq_common.pep. Scoped deliberately small per review -- proves the
enforcement boundary for exactly ONE business operation end-to-end, not
maximum MCP coverage. That operation: commercial-normalization-agent
reading a fresh FX rate (fx-rate.read, D1) -- chosen because it's a real,
already-modeled, single-condition permit with no obligations, the cleanest
possible first proof.

Skips (not fails) if either the isolated cedar-agent or the local Keycloak
isn't reachable -- same convention as test_pdp_integration.py.
"""

from __future__ import annotations

import httpx
import pytest

from rfq_common.pdp import PolicyBundle
from rfq_common.pdp.entities import ref
from rfq_common.pep import (
    AuthorizationDenied,
    ResolvedPrincipal,
    authorize_and_enforce,
    resolve_principal,
)

CEDAR_URL = "http://localhost:8280"
KEYCLOAK_URL = "http://localhost:8081"
RFQ_ROOT = __import__("pathlib").Path(__file__).resolve().parents[3]


def _cedar_up() -> bool:
    try:
        return httpx.get(f"{CEDAR_URL}/v1/policies", timeout=1.0).status_code == 200
    except Exception:
        return False


def _keycloak_up() -> bool:
    try:
        return httpx.get(f"{KEYCLOAK_URL}/realms/rfq", timeout=1.0).status_code == 200
    except Exception:
        return False


# --- resolve_principal: unit-level, claims-shape classification ------------

def test_resolve_principal_classifies_agent_by_azp():
    # iss required now: (provider, client_id) is the real lookup key --
    # client ids aren't unique across independent issuers, so classification
    # needs a real issuer to resolve against (see ClientIdCollisionError's
    # docstring / tmp/oidc-identity-unification-plan.md).
    claims = {"azp": "commercial-normalization-agent-svc", "sub": "some-service-account-sub",
              "iss": "http://localhost:8081/realms/rfq"}
    resolved = resolve_principal(claims, root=RFQ_ROOT)
    assert resolved.kind == "agent"
    assert resolved.id == "agent.commercial-normalization"


def test_resolve_principal_classifies_workload_by_azp():
    claims = {"azp": "tms-mcp-svc", "sub": "some-service-account-sub",
              "iss": "http://localhost:8081/realms/rfq"}
    resolved = resolve_principal(claims, root=RFQ_ROOT)
    assert resolved.kind == "workload"
    assert resolved.id == "workload.tms-mcp"


def test_resolve_principal_classifies_entra_v1_workload_by_appid():
    """Real client-credentials token minted from infra/entra/'s provisioned
    tenant during this pass (tmp/oidc-identity-unification-plan.md) turned
    out to be a v1.0-endpoint token: no `azp` claim at all (Entra v1 uses
    `appid` instead), issuer shaped `https://sts.windows.net/{tenant}/`, not
    `login.microsoftonline.com/.../v2.0`. This is that real shape, not a
    theoretical one -- also carries tid/oid (oid==sub, real app-only
    tokens do this), which must NOT cause a workload to misclassify as
    human (claims-contract.md's documented app-only-detection concern)."""
    claims = {
        "aud": "api://<tenant>/tms-mcp-svc",
        "iss": "https://sts.windows.net/<tenant>/",
        "appid": "581b537b-68db-485a-a9c0-9d490baf63c1",
        "appidacr": "1",
        "oid": "473ac687-11df-4ddd-b963-65814bba6d98",
        "sub": "473ac687-11df-4ddd-b963-65814bba6d98",
        "tid": "<tenant>",
        "ver": "1.0",
    }
    # register the real Entra client_id under a temp entry so this test
    # doesn't depend on identity/projections/entra.yaml's live-tenant content
    import rfq_common.pep.resolve as resolve_module
    original = resolve_module._client_id_maps
    resolve_module._client_id_maps = lambda root: (
        {}, {("entra", "581b537b-68db-485a-a9c0-9d490baf63c1"): "workload.tms-mcp"},
    )
    try:
        resolved = resolve_principal(claims, root=RFQ_ROOT)
    finally:
        resolve_module._client_id_maps = original

    assert resolved.kind == "workload"
    assert resolved.id == "workload.tms-mcp"
    assert resolved.provider == "entra"


def test_resolve_principal_rejects_azp_from_a_different_providers_registry():
    """The collision-safety point: "tms-mcp-svc" is only registered in
    identity/projections/keycloak.yaml -- presenting it under an Entra
    issuer must NOT resolve, even though the bare client_id string matches.
    Client ids are not unique across independent issuers."""
    from rfq_common.pep.resolve import PrincipalResolutionError

    claims = {"azp": "tms-mcp-svc", "sub": "some-service-account-sub",
              "iss": "https://login.microsoftonline.com/xyz/v2.0"}
    with pytest.raises(PrincipalResolutionError):
        resolve_principal(claims, root=RFQ_ROOT)


def test_client_id_maps_raises_loudly_on_provider_scoped_collision(tmp_path):
    """Two different canonical ids mapping to the same (provider, client_id)
    is a real provisioning error -- must fail loudly at load time, not
    resolve to whichever one happened to be inserted last."""
    from rfq_common.pep.resolve import ClientIdCollisionError, _client_id_maps

    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "catalog.yaml").write_text(
        "agents:\n"
        "  - id: agent-one\n"
        "    caller_identity: {oidc_client_id: shared-client-id}\n"
        "  - id: agent-two\n"
        "    caller_identity: {oidc_client_id: shared-client-id}\n",
        encoding="utf-8",
    )
    (tmp_path / "identity").mkdir()
    (tmp_path / "identity" / "projections").mkdir()
    (tmp_path / "identity" / "projections" / "keycloak.yaml").write_text(
        "clients: {}\n", encoding="utf-8",
    )

    with pytest.raises(ClientIdCollisionError):
        _client_id_maps(tmp_path)


def test_resolve_principal_classifies_human_by_oid_tid_groups():
    claims = {"sub": "mona.commercial", "oid": "x", "tid": "y", "groups": ["/rfq-commercial-emea"],
              "manager": "diane.delgado", "approval_limit_eur_cents": "1000000"}
    resolved = resolve_principal(claims, root=RFQ_ROOT)
    assert resolved.kind == "human"
    assert resolved.id == "mona.commercial"
    assert resolved.manager == "diane.delgado"
    assert resolved.approval_limit_eur_cents == 1000000


def test_resolve_principal_rejects_unclassifiable_claims():
    from rfq_common.pep.resolve import PrincipalResolutionError
    with pytest.raises(PrincipalResolutionError):
        resolve_principal({"sub": "mystery"}, root=RFQ_ROOT)


def test_resolve_principal_records_provider_from_issuer():
    kc = resolve_principal({"azp": "tms-mcp-svc", "sub": "x",
                             "iss": "http://localhost:8081/realms/rfq"}, root=RFQ_ROOT)
    assert kc.provider == "keycloak"

    # Human path doesn't depend on agent/workload client-id maps -- tid/oid/
    # groups classify it directly -- so it's the one claims shape that can
    # prove Entra provider-tagging without an identity/projections/entra.yaml
    # entry existing yet (no Entra machine identity is provisioned in this
    # repo's client-id maps today).
    entra = resolve_principal({"sub": "x", "oid": "o", "tid": "t", "groups": [],
                                "iss": "https://login.microsoftonline.com/xyz/v2.0"}, root=RFQ_ROOT)
    assert entra.provider == "entra"
    assert entra.kind == "human"


# --- One business operation, fully end-to-end -------------------------------

@pytest.fixture(scope="module")
def real_token() -> str:
    if not _keycloak_up():
        pytest.skip("Keycloak not running on :8081")
    r = httpx.post(
        f"{KEYCLOAK_URL}/realms/rfq/protocol/openid-connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "commercial-normalization-agent-svc",
            "client_secret": __import__("os").environ.get("COMMERCIAL_NORM_AGENT_SECRET", ""),
        },
    )
    if r.status_code != 200 or not __import__("os").environ.get("COMMERCIAL_NORM_AGENT_SECRET"):
        pytest.skip("COMMERCIAL_NORM_AGENT_SECRET not set -- see README for how to fetch it")
    return r.json()["access_token"]


def test_one_business_operation_end_to_end_via_real_keycloak_token(real_token):
    """Authenticated caller -> resolve_principal -> authorize_and_enforce
    -> Cedar -> AuthorizedContext -- proven with a REAL Keycloak-issued
    client-credentials token, not a hand-built claims dict."""
    if not _cedar_up():
        pytest.skip("isolated cedar-agent not running on :8280")

    import jwt  # PyJWT, already a transitive dep via python-jose/similar in this repo's tree
    claims = jwt.decode(real_token, options={"verify_signature": False})

    principal = resolve_principal(claims, root=RFQ_ROOT)
    assert principal.kind == "agent"
    assert principal.id == "agent.commercial-normalization"

    bundle = PolicyBundle.from_path(RFQ_ROOT / "authorization" / "policies.cedar")
    ctx = authorize_and_enforce(
        CEDAR_URL, bundle, principal,
        action="fx-rate.read",
        resource=ref("ExchangeRate", "CNY-EUR"),
        context={"fx_age_seconds": 720, "quote_currency": "EUR"},
        root=RFQ_ROOT,
    )
    assert ctx.decision.effect == "allow"
    assert ctx.obligations == []
    record = ctx.audit_record()
    assert record["principal_id"] == "agent.commercial-normalization"
    assert record["action"] == "fx-rate.read"
    assert record["effect"] == "allow"


def test_authorize_and_enforce_raises_on_deny():
    """Same operation, stale FX (deny path) -- proves AuthorizationDenied
    actually raises, not just returns a decision to (possibly) ignore."""
    if not _cedar_up():
        pytest.skip("isolated cedar-agent not running on :8280")

    principal = ResolvedPrincipal(kind="agent", id="agent.commercial-normalization", trust_domain="internal")
    bundle = PolicyBundle.from_path(RFQ_ROOT / "authorization" / "policies.cedar")

    with pytest.raises(AuthorizationDenied) as exc:
        authorize_and_enforce(
            CEDAR_URL, bundle, principal,
            action="fx-rate.read",
            resource=ref("ExchangeRate", "CNY-EUR"),
            context={"fx_age_seconds": 9999, "quote_currency": "EUR"},
            root=RFQ_ROOT,
        )
    assert exc.value.principal.id == "agent.commercial-normalization"
    assert exc.value.action == "fx-rate.read"
