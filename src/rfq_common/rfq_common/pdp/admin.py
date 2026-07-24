"""Cedar PDP administration clients — schema, policy, and data stores.
Identical shape to cpm-eaop's src/spike/model/pdp_admin.py, deliberately kept
separate from the runtime PDPClient (admin ops must not be reachable from
request-handling code)."""

from __future__ import annotations

import os

import httpx


def _base_url() -> str:
    return os.environ.get("CEDAR_AGENT_URL", "http://localhost:8180")


class _Store:
    def __init__(self, path: str, base_url: str | None = None):
        self._url = (base_url or _base_url()) + path

    def _put(self, payload) -> None:
        r = httpx.put(self._url, json=payload, timeout=10.0)
        r.raise_for_status()


class SchemaAdmin(_Store):
    def __init__(self, base_url: str | None = None):
        super().__init__("/v1/schema", base_url)

    def put(self, schema: dict) -> None:
        self._put(schema)


class PolicyAdmin(_Store):
    def __init__(self, base_url: str | None = None):
        super().__init__("/v1/policies", base_url)

    def put(self, policies: list[dict]) -> None:
        """policies: [{id, content}] Cedar policy texts."""
        self._put(policies)


class DataAdmin(_Store):
    def __init__(self, base_url: str | None = None):
        super().__init__("/v1/data", base_url)

    def put(self, entities: list[dict]) -> None:
        """entities: Cedar entities [{uid:{type,id}, attrs, parents}]."""
        self._put(entities)
