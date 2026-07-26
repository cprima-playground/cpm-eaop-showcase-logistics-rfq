"""M5.9: the Cedar span/metrics added to rfq_common.pep.enforce.authorize()
-- wraps the ACTUAL PDPClient.authorize() HTTP call (not a synthesized
span elsewhere), tagged with the real decision effect/determining
policies. Uses OTel's in-memory exporters, no live Collector required --
this proves the instrumentation is correct; test_observability.py
already proves the failure-semantics rule for the exporter itself.

Skips (not fails) if the isolated cedar-agent isn't reachable.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

RFQ_ROOT = Path(__file__).resolve().parents[3]
CEDAR_URL = "http://localhost:8280"


def _cedar_up() -> bool:
    try:
        return httpx.get(f"{CEDAR_URL}/v1/policies", timeout=1.0).status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def span_exporter():
    """ONE TracerProvider for the whole module, set once. OTel's
    `ProxyTracer` (what `trace.get_tracer(...)` returns at import time,
    including `rfq_common.pep.enforce`'s module-level `_tracer`) resolves
    its real tracer ONCE on first use and caches it permanently --
    calling `set_tracer_provider` again later has no effect on an
    already-resolved proxy. So this fixture must set the provider before
    ANY test in this module calls `authorize()`, and each test reads
    only the newest span(s) since the export list accumulates across the
    whole module."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))  # synchronous -- test-only, never production
    trace.set_tracer_provider(provider)
    return exporter


@pytest.fixture(scope="module")
def pdp():
    if not _cedar_up():
        pytest.skip(f"cedar-agent not running on {CEDAR_URL}")

    import sys
    sys.path.insert(0, str(RFQ_ROOT))
    import yaml
    from rfq_common.pdp import DataAdmin, PolicyAdmin, PolicyBundle, SchemaAdmin, generate_schema
    from tools.identity.gen_cedar_entities import generate_cedar_entities
    from tools.identity.validator import validate_identity

    projection = yaml.safe_load((RFQ_ROOT / "authorization" / "authz-projection.yaml").read_text(encoding="utf-8"))
    actions_doc = yaml.safe_load((RFQ_ROOT / "business" / "actions.yaml").read_text(encoding="utf-8"))
    schema = generate_schema(projection, actions_doc)
    bundle = PolicyBundle.from_path(RFQ_ROOT / "authorization" / "policies.cedar")

    model = validate_identity(
        RFQ_ROOT / "identity" / "actors.yaml", RFQ_ROOT / "identity" / "groups.yaml",
        RFQ_ROOT / "business" / "departments.yaml", RFQ_ROOT / "business" / "job-titles.yaml",
    )
    entities = generate_cedar_entities(model, RFQ_ROOT / "agents" / "catalog.yaml")

    PolicyAdmin(CEDAR_URL).put([])
    SchemaAdmin(CEDAR_URL).put(schema)
    PolicyAdmin(CEDAR_URL).put(bundle.policies())
    DataAdmin(CEDAR_URL).put(entities)
    return bundle


def test_cedar_authorize_span_carries_real_decision_attributes(pdp, span_exporter):
    from rfq_common.pdp.entities import ref
    from rfq_common.pep import ResolvedPrincipal, authorize

    principal = ResolvedPrincipal(kind="agent", id="agent.lane-evaluation", trust_domain="internal")
    authorize(
        CEDAR_URL, principal, action="capacity.check",
        resource=ref("RouteOption", "SHA-HAM-MUC"),
    )

    spans = span_exporter.get_finished_spans()
    cedar_spans = [s for s in spans if s.name == "cedar.authorize"]
    assert cedar_spans  # at least one -- module-scoped exporter accumulates across tests
    span = cedar_spans[-1]
    assert span.attributes["cedar.action"] == "capacity.check"
    assert span.attributes["cedar.principal.kind"] == "agent"
    assert span.attributes["cedar.decision.effect"] == "allow"
    assert "agent-may-check-capacity" in span.attributes["cedar.decision.determining_policies"]


def test_cedar_authorize_span_records_deny_too(pdp, span_exporter):
    """A genuine non-edge deny -- same real chain as
    test_second_hop_deny.py -- must produce a span with effect=deny, not
    only permits."""
    from rfq_common.pdp.entities import ref
    from rfq_common.pep import ResolvedPrincipal, authorize

    principal = ResolvedPrincipal(kind="agent", id="agent.route-decision", trust_domain="internal")
    authorize(
        CEDAR_URL, principal, action="agent.delegate",
        resource=ref("AgentPrincipal", "agent.commercial-normalization"),
    )

    spans = span_exporter.get_finished_spans()
    cedar_spans = [s for s in spans if s.name == "cedar.authorize"]
    assert cedar_spans
    assert cedar_spans[-1].attributes["cedar.decision.effect"] == "deny"
