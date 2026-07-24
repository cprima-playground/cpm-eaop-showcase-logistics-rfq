"""APIKEY auth -- FX is a machine-only service (no SSO, no MCP): per
systems/mock-architecture.md, FX authenticates callers with an APIKEY header,
not a human/agent identity. This authenticates the CALLER-TO-BACKEND hop; it is
NOT the Cedar authorization decision (that's a separate, correlated boundary --
ADR-008 Related)."""

from __future__ import annotations

import os

from fastapi import Header, HTTPException

DEFAULT_DEV_KEY = "dev-fx-key"  # dev-only default; real envs set FX_API_KEY (Secret Manager in test/prod)


def _expected_key() -> str:
    return os.environ.get("FX_API_KEY", DEFAULT_DEV_KEY)


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if x_api_key != _expected_key():
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")
