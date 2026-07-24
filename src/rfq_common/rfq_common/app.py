"""Base FastAPI app factory -- every mock system builds on this (ADR-006).
Health endpoint + theme CSS endpoint + a SHOWCASE banner header, common to all
systems; each system mounts its own routes on top."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import FastAPI, Response

from .clock import now
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

    return app
