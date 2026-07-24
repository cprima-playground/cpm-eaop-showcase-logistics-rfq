"""Load the showcase's schema + policies + static data into the isolated cedar-agent.

Mirrors cpm-eaop src/spike/model/pdp_bootstrap.py's order: clear policies, PUT
schema, PUT policies, PUT static data. Targets CEDAR_AGENT_URL (default the
isolated showcase instance on :8280 -- NOT cpm-eaop's :8180).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

import bundle
import entities

RFQ_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_FILE = RFQ_ROOT / "authorization" / "agentic.cedarschema"


def _base_url() -> str:
    return os.environ.get("CEDAR_AGENT_URL", "http://localhost:8280")


def load(base_url: str | None = None) -> None:
    url = base_url or _base_url()
    # clear first (matches cpm-eaop: avoid stale policies from a prior run)
    httpx.put(f"{url}/v1/policies", json=[], timeout=10.0).raise_for_status()
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    httpx.put(f"{url}/v1/schema", json=schema, timeout=10.0).raise_for_status()
    httpx.put(f"{url}/v1/policies", json=bundle.policies(), timeout=10.0).raise_for_status()
    httpx.put(f"{url}/v1/data", json=entities.static_entities(), timeout=10.0).raise_for_status()


if __name__ == "__main__":
    load()
    print(f"bootstrapped {_base_url()}")
