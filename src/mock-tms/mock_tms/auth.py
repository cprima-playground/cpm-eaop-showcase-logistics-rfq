"""APIKEY auth -- TMS is machine-only (no SSO), same posture as FX/masterdata.
Credential source (ADR-009): TMS_API_KEY env, else Vault (dev), else fail closed."""

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

    env_key = os.environ.get("TMS_API_KEY")
    if env_key:
        _cached_key = env_key
        return _cached_key

    try:
        _cached_key = SecretsClient("dev", inventory_path=INVENTORY_PATH).get("tms-api-key")
        return _cached_key
    except Exception as exc:
        raise CredentialUnavailableError(
            "tms-api-key is not available: TMS_API_KEY is unset and Vault could "
            "not supply it (docker compose up -d in infra/vault/, then uv run "
            "seed.py). Refusing to fall back to a known default."
        ) from exc


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if x_api_key != _expected_key():
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")
