"""Vault KV-v2 admin + read client (ADR-009). Raw httpx, no `hvac` dependency --
same style as rfq_common.pdp's admin/client split. Dev-only mechanism; test/prod
use GCP Secret Manager instead (see client.py)."""

from __future__ import annotations

import os

import httpx


def _base_url() -> str:
    return os.environ.get("VAULT_ADDR", "http://localhost:8200")


def _token() -> str:
    return os.environ.get("VAULT_TOKEN", "rfq-dev-root")


class VaultAdmin:
    """Write access -- used only by the seed script, never by request-handling
    code (mirrors pdp.admin's separation of admin ops from the runtime client)."""

    def __init__(self, base_url: str | None = None, token: str | None = None):
        self._base_url = base_url or _base_url()
        self._token = token or _token()

    def put(self, path: str, value: dict) -> None:
        """KV-v2 write: PUT {base}/v1/secret/data/{path} {"data": value}."""
        r = httpx.put(
            f"{self._base_url}/v1/secret/data/{path}",
            json={"data": value},
            headers={"X-Vault-Token": self._token},
            timeout=10.0,
        )
        r.raise_for_status()


class VaultReader:
    """Read-only client -- what SecretsClient uses at runtime."""

    def __init__(self, base_url: str | None = None, token: str | None = None):
        self._base_url = base_url or _base_url()
        self._token = token or _token()

    def get(self, path: str, *, key: str = "value") -> str:
        """KV-v2 read: GET {base}/v1/secret/data/{path} -> data.data[key]."""
        r = httpx.get(
            f"{self._base_url}/v1/secret/data/{path}",
            headers={"X-Vault-Token": self._token},
            timeout=10.0,
        )
        r.raise_for_status()
        data = r.json()["data"]["data"]
        if key not in data:
            raise KeyError(f"vault path {path!r} has no key {key!r}")
        return data[key]

    def health(self) -> bool:
        try:
            return httpx.get(f"{self._base_url}/v1/sys/health", timeout=2.0).status_code == 200
        except Exception:
            return False
