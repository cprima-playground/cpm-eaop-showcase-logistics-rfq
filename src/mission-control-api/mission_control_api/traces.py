"""M8.6 step 10: GET /api/v1/traces, GET /api/v1/traces/{trace_id}.
Thin Tempo search proxy, filtered on `cedar.authorize` spans (the real
span every real authorize() call emits, rfq_common/pep/enforce.py).

/traces
  -> operational observability
  -> best-effort / potentially sampled
  -> not authoritative
  -> not an audit log

/api/v1/decisions is DELIBERATELY ABSENT (D2) -- a real append-only
decision log needs its own milestone (schema, sink, retention,
PII/redaction, tamper evidence, access control, export/compliance),
decided first. Building it here would make Mission Control a second
authorization source of truth, contrary to its own design principle.

Real, separate infra finding (not fixed here, out of this step's scope):
the live compose deployment's services have no OTLP wiring to the real
observability collector at all (different Docker network, unconnected --
same class of gap the M7 stabilization pass found and fixed for
cedar-agent). Every real service's traces are currently dropped
silently (correctly, non-blocking, per M5.9's own failure-semantics
rule) rather than reaching Tempo. This module's own logic is verified
against a REAL span from the real instrumented authorize() code path,
injected directly from the host where the collector is reachable --
proving the query logic works, not that the live deployment's telemetry
pipeline is fully wired end to end."""

from __future__ import annotations

import os

import httpx

DEFAULT_TEMPO_URL = "http://tempo:3200"


def _tempo_url() -> str:
    return os.environ.get("TEMPO_URL", DEFAULT_TEMPO_URL)


def search_traces(*, limit: int = 20, timeout: float = 5.0) -> dict:
    try:
        r = httpx.get(
            f"{_tempo_url()}/api/search",
            params={"q": '{ name = "cedar.authorize" }', "limit": limit},
            timeout=timeout,
        )
        r.raise_for_status()
        body = r.json()
    except Exception as exc:
        # Observability must never become a synchronous dependency
        # (rfq_common/observability.py's own hard rule, honored here at
        # the API level too) -- Tempo being down degrades this endpoint,
        # it never 500s.
        return {"available": False, "error": str(exc), "traces": []}

    return {"available": True, "traces": body.get("traces", [])}


def get_trace(trace_id: str, *, timeout: float = 5.0) -> dict:
    try:
        r = httpx.get(f"{_tempo_url()}/api/traces/{trace_id}", timeout=timeout)
        if r.status_code == 404:
            return {"available": True, "found": False, "trace": None}
        r.raise_for_status()
        return {"available": True, "found": True, "trace": _extract_cedar_spans(r.json())}
    except Exception as exc:
        return {"available": False, "error": str(exc), "found": False, "trace": None}


def _extract_cedar_spans(raw_trace: dict) -> dict:
    """Surfaces just the fields the M8 acceptance criteria care about --
    action, principal.kind, decision.effect, determining_policies,
    correlation_id -- rather than the full raw OTLP payload."""
    spans_out = []
    for batch in raw_trace.get("batches", raw_trace.get("resourceSpans", [])):
        for scope_spans in batch.get("scopeSpans", batch.get("instrumentationLibrarySpans", [])):
            for span in scope_spans.get("spans", []):
                if span.get("name") != "cedar.authorize":
                    continue
                attrs = {a["key"]: a["value"].get("stringValue") for a in span.get("attributes", [])}
                spans_out.append({
                    "trace_id": span.get("traceId"),
                    "span_id": span.get("spanId"),
                    "action": attrs.get("cedar.action"),
                    "principal_kind": attrs.get("cedar.principal.kind"),
                    "decision_effect": attrs.get("cedar.decision.effect"),
                    "determining_policies": attrs.get("cedar.decision.determining_policies"),
                    "correlation_id": attrs.get("correlation_id"),
                })
    return {"cedar_authorize_spans": spans_out}
