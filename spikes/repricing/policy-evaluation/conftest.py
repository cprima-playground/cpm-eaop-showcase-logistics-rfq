"""Pytest fixtures for the policy-evaluation harness.

Mirrors cpm-eaop tests/test_model.py's skip-gate pattern: skip (not fail) if the
isolated cedar-agent isn't running. Bootstraps once per session against the
showcase's OWN instance (:8280 by default) -- never cpm-eaop's :8180.
"""

from __future__ import annotations

import os

import httpx
import pytest

import bootstrap
import kill_switch

CEDAR_URL = os.environ.get("CEDAR_AGENT_URL", "http://localhost:8280")


def _sidecar_up() -> bool:
    try:
        return httpx.get(f"{CEDAR_URL}/v1/policies", timeout=1.0).status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="session", autouse=True)
def pdp():
    if not _sidecar_up():
        pytest.skip(f"cedar-agent not running on {CEDAR_URL} (docker compose up -d)")
    bootstrap.load(CEDAR_URL)
    return CEDAR_URL


@pytest.fixture(autouse=True)
def _reset_kill_switch():
    kill_switch.reset()
    yield
    kill_switch.reset()
