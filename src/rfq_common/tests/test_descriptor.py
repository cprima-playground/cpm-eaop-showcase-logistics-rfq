"""M5.5: runtime service descriptor -- build_descriptor's pure-assembly
shape (no network), plus run_startup_self_check against the real stack
(reuses rfq_common.pep.preflight, already proven in
test_machine_identity_preflight.py -- this only checks the wiring: a
real failing identity must raise before a service would finish booting,
a real passing identity must not)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from rfq_common.descriptor import DESCRIPTOR_SCHEMA_VERSION, DependencyInfo, build_descriptor, run_startup_self_check
from rfq_common.pep.preflight import MachineIdentity

RFQ_ROOT = Path(__file__).resolve().parents[3]
KEYCLOAK_URL = "http://localhost:8081"


def test_build_descriptor_shape_matches_the_projection_contract():
    descriptor = build_descriptor(
        canonical_id="agent.route-decision",
        kind="a2a-agent",
        instance_id="test-instance-1",
        base_url="http://route-decision-agent:8111",
        protocol_type="a2a",
        protocol_version="1.0",
        trust_domain="internal",
        capability_source="agents/catalog.yaml",
        skills=["recommend-route"],
        dependencies=[DependencyInfo(
            canonical_id="agent.lane-evaluation", relation="a2a",
            endpoint="http://lane-evaluation-agent:8110",
        )],
    )
    assert descriptor.schema_version == DESCRIPTOR_SCHEMA_VERSION
    assert descriptor.canonical_id == "agent.route-decision"
    assert descriptor.kind == "a2a-agent"
    assert descriptor.endpoints.base_url == "http://route-decision-agent:8111"
    assert descriptor.endpoints.health == "/healthz"
    assert descriptor.endpoints.protocol.type == "a2a"
    assert descriptor.identity.expected_canonical_id == "agent.route-decision"
    assert descriptor.identity.trust_domain == "internal"
    assert descriptor.capabilities.skills == ["recommend-route"]
    assert descriptor.capabilities.tools == []
    assert descriptor.dependencies[0].canonical_id == "agent.lane-evaluation"
    assert descriptor.status.readiness == "ready"


def test_build_descriptor_accepts_control_plane_kind_and_rest_protocol():
    """M8 (1.0 -> 1.1): additive schema extension for mission-control-api,
    the schema's first real consumer -- kind="control-plane" and
    protocol_type="rest" must build cleanly, same as every existing
    a2a-agent/mcp-server descriptor does."""
    descriptor = build_descriptor(
        canonical_id="workload.mission-control", kind="control-plane", instance_id="test-instance-1",
        base_url="https://mission-control.eaop-logistics.localhost", protocol_type="rest",
        capability_source="openapi:/api/v1/openapi.json",
    )
    assert descriptor.schema_version == DESCRIPTOR_SCHEMA_VERSION
    assert descriptor.kind == "control-plane"
    assert descriptor.endpoints.protocol.type == "rest"
    assert descriptor.capabilities.skills == []
    assert descriptor.capabilities.tools == []


def test_build_descriptor_accepts_platform_kind():
    """M10 (1.1 -> 1.2): additive schema extension for geo-api -- a real,
    always-on service that is none of a2a-agent/mcp-server/control-plane,
    so kind="platform" must build cleanly, same as every other kind."""
    descriptor = build_descriptor(
        canonical_id="workload.geo-api", kind="platform", instance_id="test-instance-1",
        base_url="https://geo.eaop-logistics.localhost", protocol_type="rest",
        capability_source="static:route.geometry.compute", skills=["route.geometry.compute"],
    )
    assert descriptor.schema_version == DESCRIPTOR_SCHEMA_VERSION
    assert descriptor.kind == "platform"
    assert descriptor.endpoints.protocol.type == "rest"
    assert descriptor.capabilities.skills == ["route.geometry.compute"]


def test_canonical_id_is_stable_across_instances_instance_id_is_not():
    """canonical_id = logical service identity (what a future registry's
    RESOLVE keys by); instance_id = this one process (new every boot).
    Two descriptors for the SAME service, different processes, must
    share canonical_id but never instance_id."""
    from rfq_common.descriptor import new_instance_id

    first = build_descriptor(
        canonical_id="agent.lane-evaluation", kind="a2a-agent", instance_id=new_instance_id(),
        base_url="http://lane-evaluation-agent-1:8110", protocol_type="a2a",
        capability_source="agents/catalog.yaml", skills=["evaluate-lane-capacity"],
    )
    second = build_descriptor(
        canonical_id="agent.lane-evaluation", kind="a2a-agent", instance_id=new_instance_id(),
        base_url="http://lane-evaluation-agent-2:8110", protocol_type="a2a",
        capability_source="agents/catalog.yaml", skills=["evaluate-lane-capacity"],
    )
    assert first.canonical_id == second.canonical_id
    assert first.instance_id != second.instance_id


def test_descriptor_never_carries_secrets_or_request_scoped_fields():
    """Structural guarantee, not just a convention: ServiceDescriptor's
    schema has no field for a secret/token/correlation_id/root_requester
    -- so a caller literally cannot pass one through even by mistake."""
    descriptor = build_descriptor(
        canonical_id="workload.tms-mcp", kind="mcp-server", instance_id="i-1",
        base_url="http://tms-mcp:8120", protocol_type="mcp",
        capability_source="interfaces/mcp/tools.yaml", tools=["check_lane_capacity"],
    )
    dumped = descriptor.model_dump()
    forbidden_substrings = ("secret", "token", "correlation_id", "root_requester", "parent_task_id", "delegated_by")
    dumped_text = str(dumped).lower()
    for forbidden in forbidden_substrings:
        assert forbidden not in dumped_text, f"descriptor schema leaked a {forbidden!r}-shaped field"


def _keycloak_up() -> bool:
    try:
        return httpx.get(f"{KEYCLOAK_URL}/realms/rfq", timeout=1.0).status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def preconditions():
    if not _keycloak_up():
        pytest.skip(f"Keycloak not running on {KEYCLOAK_URL}")


@pytest.mark.asyncio
async def test_startup_self_check_passes_for_a_real_valid_identity(preconditions):
    identity = MachineIdentity(
        canonical_id="agent.lane-evaluation", kind="agent",
        client_id="lane-evaluation-agent-svc", secret_name="lane-evaluation-agent-client-secret",
    )
    result = await run_startup_self_check(identity, oidc_issuer_url=KEYCLOAK_URL, root=RFQ_ROOT)
    assert result.ok
    assert result.resolved_id == "agent.lane-evaluation"


@pytest.mark.asyncio
async def test_startup_self_check_raises_for_a_mismatched_expected_id(preconditions):
    """The wiring this test protects: if EXPECTED_CANONICAL_ID is
    misconfigured (points at the wrong identity for this deployment), the
    service must fail to start rather than boot serving under the wrong
    identity."""
    identity = MachineIdentity(
        canonical_id="agent.route-decision",  # real secret, but WRONG expected id
        kind="agent",
        client_id="lane-evaluation-agent-svc", secret_name="lane-evaluation-agent-client-secret",
    )
    with pytest.raises(RuntimeError, match="startup identity self-check failed"):
        await run_startup_self_check(identity, oidc_issuer_url=KEYCLOAK_URL, root=RFQ_ROOT)
