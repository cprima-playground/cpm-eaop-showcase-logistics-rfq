"""M8.3: shared health-probe semantics, extracted from
src/ops-dashboard/ops_dashboard/api.py's `_check_service`/`_check_vault`/
`_check_cedar`/`_check_identity_provider` (lines 105-150, 153-193,
196-238, 270-313 at extraction time) -- real, hard-won semantics, not
reinvented: Vault sealed-but-responding is `warn`, not `fail` (a sealed
vault answers, but every real secret read still fails); cedar-agent
reachable-but-zero-policies is `warn` (silently denies every future
authorize() call, a false "up"); Keycloak's issuer must match the
configured issuer exactly (a Host-header-derived mismatch breaks every
real login silently -- this repo hit this for real, M7's live-stack
stabilization pass).

ops-dashboard is NOT modified by this extraction (M8's D4) -- its own
`_check_*` functions stay exactly as they are until a later milestone
(M9) deletes them in favor of calling mission-control-api's
GET /api/v1/health instead. Temporary duplication, accepted and
time-boxed.

Deliberately simpler than ops-dashboard's `_check_service`: no per-system
authenticated-call probe (that requires holding every business system's
own API key, which mission-control-api never does -- see D3's
credential-free posture, same principle applied here). Reachability
(GET /healthz) is the only signal for a generic service; Vault/cedar-
agent/Keycloak get their own richer pass/warn/fail semantics because
their health genuinely depends on more than "did it answer"."""

from __future__ import annotations

import time
from typing import Literal

import httpx
from pydantic import BaseModel


class ProbeResult(BaseModel):
    name: str
    base_url: str
    status: Literal["pass", "warn", "fail"] = "fail"
    reachable: bool = False
    authenticated: bool = False
    reachable_basis: str
    auth_basis: str
    latency_ms: int | None = None
    detail: str | None = None


def probe_http_service(name: str, base_url: str, *, timeout: float = 3.0) -> ProbeResult:
    """Generic reachability-only probe -- GET {base_url}/healthz. No
    authenticated call (see module docstring); `pass` == 200, `fail`
    otherwise. Never raises -- a degraded peer must never break the
    caller's aggregate response."""
    result = ProbeResult(
        name=name, base_url=base_url,
        reachable_basis=f"GET {base_url}/healthz", auth_basis="not checked (reachability only)",
    )
    t0 = time.monotonic()
    try:
        r = httpx.get(f"{base_url}/healthz", timeout=timeout)
    except httpx.HTTPError as exc:
        result.detail = f"unreachable: {exc}"
        return result
    result.latency_ms = round((time.monotonic() - t0) * 1000)
    result.reachable = r.status_code == 200
    if not result.reachable:
        result.detail = f"/healthz returned {r.status_code}"
        return result
    result.authenticated = True  # no separate auth dimension for a generic probe
    result.status = "pass"
    return result


def probe_vault(name: str, vault_addr: str, *, timeout: float = 3.0) -> ProbeResult:
    """`/v1/sys/health` needs no token -- reachability is "responds at
    all" (Vault uses non-200 status codes as signal, not just 200); the
    auth-equivalent is unsealed+initialized."""
    result = ProbeResult(
        name=name, base_url=vault_addr,
        reachable_basis=f"GET {vault_addr}/v1/sys/health (any response at all, incl. Vault's non-200 status codes)",
        auth_basis="response body has initialized=true and sealed=false",
    )
    t0 = time.monotonic()
    try:
        r = httpx.get(f"{vault_addr}/v1/sys/health", timeout=timeout)
    except httpx.HTTPError as exc:
        result.detail = f"unreachable: {exc}"
        return result
    result.latency_ms = round((time.monotonic() - t0) * 1000)
    result.reachable = r.status_code in (200, 429, 472, 473, 501, 503)
    if not result.reachable:
        result.detail = f"/v1/sys/health returned {r.status_code}"
        return result

    try:
        body = r.json()
    except ValueError:
        result.detail = "/v1/sys/health did not return valid JSON"
        result.status = "warn"
        return result

    if body.get("initialized") and not body.get("sealed"):
        result.authenticated = True
        result.status = "pass"
    else:
        result.detail = f"initialized={body.get('initialized')}, sealed={body.get('sealed')}"
        result.status = "warn"
    return result


def probe_cedar(name: str, base_url: str, *, timeout: float = 3.0) -> ProbeResult:
    """No API key (cedar-agent has no auth of its own) -- reachability is
    `GET /v1/policies` answering at all; the auth-equivalent is at least
    one policy actually loaded (a reachable-but-empty agent would
    silently deny everything, same class of false-"up" as Vault
    sealed-but-responding)."""
    result = ProbeResult(
        name=name, base_url=base_url,
        reachable_basis=f"GET {base_url}/v1/policies",
        auth_basis="at least one policy is actually loaded (a reachable-but-empty agent silently denies everything)",
    )
    t0 = time.monotonic()
    try:
        r = httpx.get(f"{base_url}/v1/policies", timeout=timeout)
    except httpx.HTTPError as exc:
        result.detail = f"unreachable: {exc}"
        return result
    result.latency_ms = round((time.monotonic() - t0) * 1000)
    result.reachable = r.status_code == 200
    if not result.reachable:
        result.detail = f"/v1/policies returned {r.status_code}"
        return result

    try:
        policies = r.json()
    except ValueError:
        result.detail = "/v1/policies did not return valid JSON"
        result.status = "warn"
        return result

    if policies:
        result.authenticated = True
        result.status = "pass"
    else:
        result.detail = "reachable but zero policies loaded -- every authorize() call will deny"
        result.status = "warn"
    return result


def probe_oidc_issuer(name: str, issuer_url: str, *, timeout: float = 3.0, verify=True) -> ProbeResult:
    """Reachability is the OIDC discovery document loading at all; the
    auth-equivalent is its `issuer` field matching the configured issuer
    exactly -- a Host-header-derived mismatch breaks every real login
    silently (Keycloak derives `iss` from whatever Host header reached
    it; this repo hit this for real during M7's live-stack
    stabilization)."""
    result = ProbeResult(
        name=name, base_url=issuer_url,
        reachable_basis=f"GET {issuer_url}/.well-known/openid-configuration",
        auth_basis=f"the discovery doc's 'issuer' field equals the configured issuer ({issuer_url})",
    )
    t0 = time.monotonic()
    try:
        r = httpx.get(f"{issuer_url}/.well-known/openid-configuration", timeout=timeout, verify=verify)
    except httpx.HTTPError as exc:
        result.detail = f"unreachable: {exc}"
        return result
    result.latency_ms = round((time.monotonic() - t0) * 1000)
    result.reachable = r.status_code == 200
    if not result.reachable:
        result.detail = f"discovery doc returned {r.status_code}"
        return result

    try:
        doc_issuer = r.json().get("issuer")
    except ValueError:
        result.detail = "discovery doc was not valid JSON"
        result.status = "warn"
        return result
    if doc_issuer == issuer_url:
        result.authenticated = True
        result.status = "pass"
    else:
        result.detail = f"issuer mismatch: configured {issuer_url!r}, discovery doc says {doc_issuer!r}"
        result.status = "warn"
    return result
