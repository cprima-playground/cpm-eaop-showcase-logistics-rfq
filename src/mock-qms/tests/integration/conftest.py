"""Shared live-service skip-gate helper for integration/ tests -- factored
out of test_sso_integration.py's own duplicated `_xxx_up()` pattern so
future integration tests (and business/'s conftest.py) reuse this instead
of re-copy-pasting it."""

import httpx


def service_up(url: str, *, timeout: float = 1.0, verify=True) -> bool:
    try:
        return httpx.get(url, timeout=timeout, verify=verify).status_code == 200
    except Exception:
        return False
