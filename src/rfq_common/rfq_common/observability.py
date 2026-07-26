"""M5.9: the single observability initialization contract every A2A
agent / MCP server calls once at startup -- the observability-layer
equivalent of M5.5's `rfq_common.settings`. Establishes tracing, metrics,
and (via `instrument_app`) automatic W3C trace propagation + correlation
enrichment together, instead of each service inventing its own setup.

Design decision (per direct instruction): instrument once, through
OpenTelemetry, never against a GCP-specific or Prometheus-specific API
directly. Switching `environment` changes exporter configuration only --
never application instrumentation.

HARD RULE, telemetry failure semantics (per direct instruction):
Observability must never become a synchronous dependency of business
execution.

    collector unavailable   -> application continues
    export failure           -> telemetry dropped/buffered per SDK policy
    Prometheus unavailable   -> application continues

This module may validate configuration SYNTAX (a malformed endpoint);
it must NEVER block or fail the caller on collector/exporter
REACHABILITY. Concretely: `BatchSpanProcessor`/`PeriodicExportingMetric
Reader` already export asynchronously off the request path per the OTel
SDK's own default (this module does not defeat that default with a
synchronous exporter or a startup connectivity probe), and every setup
step here is wrapped so a genuine config/library error is logged, never
raised -- a broken telemetry stack must not stop a service from serving
real traffic.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("rfq_common.observability")

_OTEL_ENABLED_ENV = "OTEL_ENABLED"
_PROMETHEUS_ENABLED_ENV = "PROMETHEUS_ENABLED"
_DEFAULT_OTLP_ENDPOINT = "http://localhost:4317"

_httpx_instrumented = False  # module-level guard -- HTTPXClientInstrumentor().instrument() is process-global; calling it twice (e.g. two services imported in the same test process) would double-wrap


def _bool_env(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


def otel_enabled() -> bool:
    return _bool_env(_OTEL_ENABLED_ENV, default=True)


def prometheus_enabled() -> bool:
    """Independent of OTEL_ENABLED -- answers a different question
    (which consumer sees the metrics), not whether telemetry runs at
    all. Informational at this layer: the real gate is the Collector's
    own pipeline config (infra/observability/otel-collector-config.yaml);
    this flag exists so callers/tests can assert the correct posture
    without parsing that YAML, and so a future toggle that actually
    switches Collector pipelines has a stable name to key off of."""
    return _bool_env(_PROMETHEUS_ENABLED_ENV, default=True)


def configure_observability(
    *,
    service_name: str,
    canonical_id: str,
    instance_id: str,
    environment: str,
    service_version: str = "0.1.0",
) -> None:
    """Sets the process-global TracerProvider/MeterProvider. Safe to call
    at most once per process (repeated calls are a no-op after the
    first -- the OTel SDK warns but does not error on a second
    set_tracer_provider/set_meter_provider; this function does not
    special-case that, the SDK's own behavior is enough).

    `instance_id` MUST be the same value passed to `descriptor.
    build_descriptor`'s `instance_id` param (via `descriptor.
    new_instance_id()`) -- one identity, two projections
    (`/descriptor`'s JSON and every span/metric this process emits),
    never two ids for the same running process."""
    if not otel_enabled():
        logger.info("OTEL_ENABLED=false -- observability disabled, no-op SDK providers stay active")
        return

    try:
        _configure_real_providers(
            service_name=service_name, canonical_id=canonical_id, instance_id=instance_id,
            environment=environment, service_version=service_version,
        )
    except Exception:
        # Config/library errors (a malformed OTEL_EXPORTER_OTLP_ENDPOINT,
        # an incompatible SDK version) are real bugs worth logging loudly
        # -- but per the hard rule above, NEVER worth failing startup
        # over. The no-op providers the SDK ships by default remain
        # active; the service serves real traffic either way.
        logger.exception("failed to configure OpenTelemetry -- continuing without it (never a startup blocker)")


def _configure_real_providers(
    *, service_name: str, canonical_id: str, instance_id: str, environment: str, service_version: str,
) -> None:
    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", _DEFAULT_OTLP_ENDPOINT)

    # Canonical resource attribute set (M5.9) -- defined once, reused by
    # every span/metric this process emits, never invented per service.
    resource = Resource.create({
        "service.name": service_name,
        "service.instance.id": instance_id,
        "service.version": service_version,
        "deployment.environment.name": environment,
        "rfq.canonical_id": canonical_id,
    })

    tracer_provider = TracerProvider(resource=resource)
    # BatchSpanProcessor: async, non-blocking export off a background
    # thread -- this IS the failure-semantics rule, not just documented
    # alongside it. A synchronous SimpleSpanProcessor would make every
    # request pay for (or block on) a Collector round-trip; never use one
    # here.
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
    trace.set_tracer_provider(tracer_provider)

    metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=endpoint, insecure=True))
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    logger.info(
        "OpenTelemetry configured: service=%s canonical_id=%s instance=%s environment=%s endpoint=%s prometheus_enabled=%s",
        service_name, canonical_id, instance_id, environment, endpoint, prometheus_enabled(),
    )


def instrument_app(app):
    """Call once per FastAPI app, right before `create_app()` returns it
    (`rfq_common/app.py`). No-op when OTEL_ENABLED=false. Auto-
    instruments BOTH directions:
      - inbound: FastAPIInstrumentor extracts W3C traceparent from the
        ASGI request and starts a child span automatically -- no manual
        header-parsing needed anywhere in mcp_auth or A2A request
        handling.
      - outbound: HTTPXClientInstrumentor injects traceparent into every
        httpx.Client/AsyncClient call, process-wide -- every service in
        this repo already constructs plain httpx clients (confirmed
        across all 7 real services), so this covers A2A, MCP, and
        business-API calls with zero per-service code changes.
    Returns `app` unchanged, for chaining."""
    global _httpx_instrumented
    if not otel_enabled():
        return app

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)

        if not _httpx_instrumented:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
            HTTPXClientInstrumentor().instrument()
            _httpx_instrumented = True
    except Exception:
        logger.exception("failed to instrument app for OpenTelemetry -- continuing without it")

    return app
