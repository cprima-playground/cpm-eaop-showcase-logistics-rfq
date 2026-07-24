"""Shared web-frontend scaffolding for every human-facing system (ops-dashboard
today; HITL/QMS next, per build-plan.md). Centralizes what would otherwise be
copy-pasted per system: the base Jinja layout (header/nav/footer chrome) and
themed HTTP-error rendering -- so a second/third frontend doesn't duplicate it
or drift from it.

Usage: `Jinja2Templates(directory=[app_templates_dir, SHARED_TEMPLATES_DIR])`
(app dir first -- a system can still shadow a shared template by name if it
ever needs to), then `install_error_handlers(app, templates, base_context)`.
Mount SHARED_STATIC_DIR alongside the app's own static dir under a distinct
path (e.g. `/static-shared`) -- StaticFiles, unlike Jinja2Templates, takes
only one directory per mount, so it can't be combined the same way.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException

SHARED_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
SHARED_STATIC_DIR = Path(__file__).resolve().parent / "static"


def install_error_handlers(
    app: FastAPI,
    templates: Jinja2Templates,
    base_context: Callable[[Request], dict],
) -> None:
    """Themed HTML error rendering for raised HTTPExceptions (404/403/etc,
    plus the 303-redirect-to-login convention) and truly unhandled exceptions
    (500) -- every system's error pages share the same layout instead of each
    hand-rolling its own `<h1>{code}</h1>` fragment (or leaking a raw
    traceback page).

    Registered on starlette.exceptions.HTTPException (not fastapi.HTTPException,
    a subclass): Starlette's router raises the base class directly for a
    genuinely unmatched route (no view ever runs), which a handler registered
    only on the subclass would miss -- those 404s would keep falling through
    to FastAPI's own default JSON handler."""

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException):
        if exc.status_code == 303:
            return RedirectResponse(exc.headers["Location"])
        return templates.TemplateResponse(
            request, "error.html",
            {**base_context(request), "status_code": exc.status_code, "detail": exc.detail},
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception):
        return templates.TemplateResponse(
            request, "error.html",
            {**base_context(request), "status_code": 500, "detail": "Internal Server Error"},
            status_code=500,
        )
