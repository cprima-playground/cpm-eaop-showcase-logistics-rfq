"""Cross-cutting control, added before M6b per direct instruction: the
recurring stale-Vault-secret incidents across M5/M6a (found reactively,
each time, while debugging an unrelated test failure) are now a real
architectural test concern, not a one-off fix. This belongs with the
machine-identity inventory M6 already requires (decision #8) -- it's
that inventory's live, automated half: every real machine identity
currently declared by the directory (agents/catalog.yaml + identity/
projections/keycloak.yaml) must have a Vault secret that actually
authenticates, not just exists.

Deliberately does NOT compare Vault's secret value against Keycloak's
live client-secret admin API -- per direct instruction, the stronger
test is that the stored credential actually authenticates: secret
exists -> grant succeeds -> resolves to the expected canonical_id. A
value comparison can silently pass/fail for reasons unrelated to whether
authentication itself would work; a failed grant cannot.

Skips (not fails) if Keycloak/cedar-agent aren't reachable -- same
posture as every other real-stack test in this repo.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from rfq_common.pep import discover_machine_identities, preflight_machine_identity

RFQ_ROOT = Path(__file__).resolve().parents[3]
KEYCLOAK_URL = "http://localhost:8081"


def _keycloak_up() -> bool:
    try:
        return httpx.get(f"{KEYCLOAK_URL}/realms/rfq", timeout=1.0).status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def preconditions():
    if not _keycloak_up():
        pytest.skip(f"Keycloak not running on {KEYCLOAK_URL}")


def test_discovers_every_real_machine_identity_used_by_m5_and_m6a(preconditions):
    """A subset assertion, not exact-set: identity/projections/keycloak.yaml
    already declares workload entries for rate-mcp/qms-mcp/approval-mcp
    ahead of M6 actually building those servers (status: planned in
    identity/credentials-inventory.yaml -- no Vault secret yet, so they'd
    correctly fail preflight_machine_identity today; this test only
    documents the M5/M6a-scoped roster this milestone's control covers).
    Grows automatically as M6 lands real servers for them -- derived from
    the same catalog.yaml + keycloak.yaml projection data
    resolve_principal itself uses, not a separately maintained list."""
    identities = discover_machine_identities(RFQ_ROOT)
    canonical_ids = {i.canonical_id for i in identities}
    assert canonical_ids >= {
        "agent.lane-evaluation",
        "agent.route-decision",
        "agent.commercial-normalization",
        "agent.trust-boundary-fixture",
        "workload.tms-mcp",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("canonical_id", [
    "agent.lane-evaluation",
    "agent.route-decision",
    "agent.commercial-normalization",
    "agent.trust-boundary-fixture",
    "workload.tms-mcp",
])
async def test_machine_identity_preflight(preconditions, canonical_id):
    """secret exists in Vault -> Keycloak accepts a client-credentials
    grant against it -> the resulting token resolves (via the real
    authenticate_request path every MCP/A2A boundary uses) to the
    expected canonical_id. Any one of the three failing is a real
    deployment defect this repo has hit before -- not a hypothetical."""
    identities = {i.canonical_id: i for i in discover_machine_identities(RFQ_ROOT)}
    identity = identities[canonical_id]
    result = await preflight_machine_identity(identity, oidc_issuer_url=KEYCLOAK_URL, root=RFQ_ROOT)
    assert result.ok, (
        f"{canonical_id}: secret_ok={result.secret_ok} grant_ok={result.grant_ok} "
        f"resolves_ok={result.resolves_ok} resolved_id={result.resolved_id!r} error={result.error}"
    )
