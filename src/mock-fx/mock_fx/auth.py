"""APIKEY auth -- FX is a machine-only service (no SSO, no MCP): per
systems/mock-architecture.md, FX authenticates callers with an APIKEY header,
not a human/agent identity. This authenticates the CALLER-TO-BACKEND hop; it is
NOT the Cedar authorization decision (that's a separate, correlated boundary --
ADR-008 Related).

Credential source (ADR-009, KNOWN-ISSUES.md #1 -- no more hardcoded default):
1. FX_API_KEY env var, if set -- what tests use, Vault-independent.
2. else rfq_common.secrets.SecretsClient("dev").get("fx-api-key") -- Vault.
3. else fail closed: raise at first use, never silently accept a known value.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Header, HTTPException

from rfq_common.secrets import SecretsClient

RFQ_ROOT = Path(__file__).resolve().parents[3]
INVENTORY_PATH = RFQ_ROOT / "identity" / "credentials-inventory.yaml"

_cached_key: str | None = None


class CredentialUnavailableError(RuntimeError):
    pass


def _expected_key() -> str:
    global _cached_key
    if _cached_key is not None:
        return _cached_key

    env_key = os.environ.get("FX_API_KEY")
    if env_key:
        _cached_key = env_key
        return _cached_key

    try:
        _cached_key = SecretsClient("dev", inventory_path=INVENTORY_PATH).get("fx-api-key")
        return _cached_key
    except Exception as exc:
        raise CredentialUnavailableError(
            "fx-api-key is not available: FX_API_KEY is unset and Vault could not "
            "supply it (docker compose up -d in infra/vault/, then uv run seed.py). "
            "Refusing to fall back to a known default."
        ) from exc


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if x_api_key != _expected_key():
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")
