"""M5.9: rfq_common.observability -- unit-level (no live Collector
required). Proves: the OTEL_ENABLED/PROMETHEUS_ENABLED toggles work
independently, configure_observability() never raises even when the
OTLP endpoint is unreachable (the hard failure-semantics rule), and the
canonical resource attribute set is exactly what the plan specifies.
"""

from __future__ import annotations

import logging

import pytest

from rfq_common import observability


@pytest.fixture(autouse=True)
def _reset_providers(monkeypatch):
    """Each test gets a fresh global tracer/meter provider state --
    otherwise the "first call wins" OTel SDK behavior would make test
    order matter."""
    import opentelemetry.metrics._internal as metrics_internal
    from opentelemetry import trace

    def _reset():
        # set_tracer_provider/set_meter_provider each gate re-assignment
        # behind a private `Once` guard, not just the provider variable
        # itself -- both must be reset or the second test in a session
        # silently keeps the first test's provider (proxy warning logged,
        # no error), making test order matter. Test-only reset, not
        # something application code should ever need.
        trace._TRACER_PROVIDER = None
        trace._TRACER_PROVIDER_SET_ONCE = trace.Once()
        metrics_internal._METER_PROVIDER = None
        metrics_internal._METER_PROVIDER_SET_ONCE = metrics_internal.Once()
        observability._httpx_instrumented = False

    _reset()
    yield
    _reset()


def test_otel_enabled_defaults_true(monkeypatch):
    monkeypatch.delenv("OTEL_ENABLED", raising=False)
    assert observability.otel_enabled() is True


def test_otel_enabled_false_values(monkeypatch):
    for value in ("false", "0", "no", "off", "FALSE"):
        monkeypatch.setenv("OTEL_ENABLED", value)
        assert observability.otel_enabled() is False, value


def test_prometheus_enabled_independent_of_otel_enabled(monkeypatch):
    """The two toggles answer different questions -- must be settable
    independently, not coupled."""
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.setenv("PROMETHEUS_ENABLED", "false")
    assert observability.otel_enabled() is True
    assert observability.prometheus_enabled() is False

    monkeypatch.setenv("OTEL_ENABLED", "false")
    monkeypatch.setenv("PROMETHEUS_ENABLED", "true")
    assert observability.otel_enabled() is False
    assert observability.prometheus_enabled() is True


def test_configure_observability_disabled_is_a_real_noop(monkeypatch):
    """OTEL_ENABLED=false must not even attempt SDK setup -- assert via
    the global tracer provider staying the SDK's own default no-op type,
    not a real TracerProvider."""
    from opentelemetry import trace

    monkeypatch.setenv("OTEL_ENABLED", "false")
    observability.configure_observability(
        service_name="test-svc", canonical_id="agent.test", instance_id="i-1", environment="local",
    )
    provider = trace.get_tracer_provider()
    assert type(provider).__name__ != "TracerProvider"  # stayed the SDK's no-op default


def test_configure_observability_survives_unreachable_endpoint(monkeypatch):
    """THE hard rule, proven concretely: a genuinely unreachable OTLP
    endpoint must not raise out of configure_observability(), and a real
    span emitted afterward must not raise either -- BatchSpanProcessor's
    export happens on a background thread, off the request path, exactly
    as the failure-semantics rule requires."""
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:1")  # nothing listens here

    observability.configure_observability(
        service_name="test-svc", canonical_id="agent.test", instance_id="i-1", environment="local",
    )

    from opentelemetry import trace
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("survives-unreachable-collector") as span:
        span.set_attribute("proves", "business-logic-continues")
    # No exception raised above -- that IS the proof. Explicit assert for
    # readability, not because there's anything else to check.
    assert True


def test_configure_observability_sets_canonical_resource_attributes(monkeypatch):
    """The canonical resource attribute set, exactly -- service.name,
    service.instance.id (== the instance_id param, same value descriptor.
    new_instance_id() would have produced), service.version,
    deployment.environment.name, rfq.canonical_id."""
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:1")

    observability.configure_observability(
        service_name="lane-evaluation-agent", canonical_id="agent.lane-evaluation",
        instance_id="instance-abc-123", environment="local", service_version="0.1.0",
    )

    from opentelemetry import trace
    provider = trace.get_tracer_provider()
    attrs = dict(provider.resource.attributes)
    assert attrs["service.name"] == "lane-evaluation-agent"
    assert attrs["service.instance.id"] == "instance-abc-123"
    assert attrs["service.version"] == "0.1.0"
    assert attrs["deployment.environment.name"] == "local"
    assert attrs["rfq.canonical_id"] == "agent.lane-evaluation"


def test_configure_observability_logs_but_never_raises_on_setup_error(monkeypatch, caplog):
    """A genuine config/library error during setup (simulated here by
    monkeypatching the real setup function to raise) must be logged, not
    propagated -- the hard rule applies to bugs in this module too, not
    just to network failures."""
    def _boom(**kwargs):
        raise RuntimeError("simulated config error")

    monkeypatch.setattr(observability, "_configure_real_providers", _boom)
    with caplog.at_level(logging.ERROR):
        observability.configure_observability(
            service_name="test-svc", canonical_id="agent.test", instance_id="i-1", environment="local",
        )
    assert "failed to configure OpenTelemetry" in caplog.text


def test_instrument_app_disabled_is_a_real_noop(monkeypatch):
    from fastapi import FastAPI

    monkeypatch.setenv("OTEL_ENABLED", "false")
    app = FastAPI()
    returned = observability.instrument_app(app)
    assert returned is app
    # No instrumentation middleware/state should have been added -- the
    # cheapest real signal is that instrument_app didn't touch the httpx
    # global instrumentation guard.
    assert observability._httpx_instrumented is False


def test_instrument_app_enabled_instruments_fastapi_and_httpx_once(monkeypatch):
    from fastapi import FastAPI

    monkeypatch.setenv("OTEL_ENABLED", "true")
    app1 = FastAPI()
    app2 = FastAPI()
    observability.instrument_app(app1)
    assert observability._httpx_instrumented is True
    # Second app, second call -- httpx instrumentation must not be
    # attempted twice (process-global, would double-wrap) -- the guard
    # flag must stay True, not toggle or re-run.
    observability.instrument_app(app2)
    assert observability._httpx_instrumented is True
