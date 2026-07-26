"""Base FastAPI app factory -- every mock system builds on this (ADR-006).
Health endpoint + theme CSS endpoint + a SHOWCASE banner header + a
correlation-id header, common to all systems; each system mounts its own
routes on top."""

from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import FastAPI, Request, Response
from opentelemetry import baggage, context as otel_context, trace

from .clock import now
from .observability import instrument_app
from .theme import ThemePack, render_css_vars


def create_app(name: str, *, system_id: str | None = None,
               theme_pack: ThemePack | None = None) -> FastAPI:
    """`name` is the system's display name (e.g. "Mock QMS"). `system_id` (e.g.
    "qms") selects that system's accent from the theme pack's `systems` map."""
    # /swagger not the FastAPI default /docs -- distinct from this app's own
    # generic "docs" concept (READMEs, /status page links); ReDoc stays at its
    # default /redoc as the second, alternative spec viewer.
    app = FastAPI(title=name, version="v0.1", docs_url="/swagger", redoc_url="/redoc")
    app.state.theme_pack = theme_pack
    app.state.system_id = system_id

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "system": name, "now": now().isoformat()}

    @app.get("/_theme.css")
    def theme_css() -> Response:
        pack = app.state.theme_pack
        if pack is None:
            return Response(":root {}", media_type="text/css")
        css = render_css_vars(pack, system_id=app.state.system_id)
        return Response(css, media_type="text/css")

    @app.middleware("http")
    async def _showcase_banner(request, call_next):
        response = await call_next(request)
        pack = app.state.theme_pack
        if pack is not None and pack.banner.show and pack.banner.text:
            # HTTP header values are latin-1 only; percent-encode losslessly
            # (banner text may contain non-ASCII, e.g. an em dash).
            response.headers["X-Showcase-Banner"] = quote(pack.banner.text)
        return response

    @app.middleware("http")
    async def _correlation_id(request: Request, call_next):
        # Reuse an inbound id (header, or OTel baggage carried by an
        # upstream hop's instrumented httpx call) so the SAME journey id
        # survives multi-hop A2A/MCP chains; only the true entry point
        # generates a fresh one.
        inbound = request.headers.get("x-correlation-id") or baggage.get_baggage("correlation_id")
        request.state.correlation_id = inbound or str(uuid.uuid4())
        # Enrichment, NOT replacement (M5.9) -- request.state/X-Correlation-Id
        # above is unchanged; this just joins the SAME id onto whatever span
        # FastAPIInstrumentor already started for this request (a no-op,
        # non-recording span if OTel isn't configured -- always safe to call).
        trace.get_current_span().set_attribute("correlation_id", request.state.correlation_id)
        # Propagate via baggage so HTTPXClientInstrumentor auto-injects it
        # on every outbound call this request makes, with zero per-call-site
        # changes at any A2A/MCP client -- same mechanism as W3C traceparent.
        ctx = baggage.set_baggage("correlation_id", request.state.correlation_id)
        token = otel_context.attach(ctx)
        try:
            response = await call_next(request)
        finally:
            otel_context.detach(token)
        response.headers["X-Correlation-Id"] = request.state.correlation_id
        return response

    return instrument_app(app)
