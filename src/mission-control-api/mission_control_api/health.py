"""M8.3 step 6: GET /api/v1/health. Its OWN health-target roster (D9) --
a DIFFERENT, BROADER set than /api/v1/services' registry roster. The 5
mock-* business systems and Keycloak/cedar-agent/Vault are real,
legitimate health-probe targets even though none of them is ever a
registry entry (no /descriptor exists on any of them) -- registry
membership and health-probe membership are two different questions
answered by two different rosters (see api.py's module docstring)."""

from __future__ import annotations

import os
from pathlib import Path

from rfq_common.probe import ProbeResult, probe_cedar, probe_http_service, probe_oidc_issuer, probe_vault
from rfq_common.service_resolver import EnvironmentServiceResolver

from .registry import ObservedServiceRegistry, registry_roster

# Business systems -- never registry entries (no /descriptor), still
# real health-probe targets. Env var names match the existing convention
# other services already use for these same downstream URLs
# (compose.showcase.yaml's mock-qms/ops-dashboard blocks).
_MOCK_SYSTEM_ENV = {
    "mock-masterdata": "MASTERDATA_URL",
    "mock-tms": "TMS_URL",
    "mock-rate": "RATE_URL",
    "mock-fx": "FX_URL",
    "mock-qms": "QMS_URL",
}


def _mock_system_resolver() -> EnvironmentServiceResolver:
    return EnvironmentServiceResolver(dict(_MOCK_SYSTEM_ENV))


def health_report(registry: ObservedServiceRegistry, root: Path | None = None) -> dict:
    results: list[ProbeResult] = []

    # 7 registry services -- reachability only (already-live /descriptor
    # implies more than /healthz alone would, but this probe is
    # independent of the registry's own cache so a stale registry entry
    # never masks a real outage).
    for canonical_id in registry_roster(root):
        try:
            base_url = registry.resolve_endpoint(canonical_id)
        except Exception as exc:
            results.append(ProbeResult(
                name=canonical_id, base_url="", status="fail",
                reachable_basis="endpoint resolution", auth_basis="not checked",
                detail=f"could not resolve endpoint: {exc}",
            ))
            continue
        results.append(probe_http_service(canonical_id, base_url))

    # 5 mock-* business systems -- reachability only, same as above.
    mock_resolver = _mock_system_resolver()
    for name, env_var in _MOCK_SYSTEM_ENV.items():
        base_url = os.environ.get(env_var)
        if not base_url:
            results.append(ProbeResult(
                name=name, base_url="", status="fail",
                reachable_basis=f"env var {env_var}", auth_basis="not checked",
                detail=f"{env_var} not set",
            ))
            continue
        results.append(probe_http_service(name, base_url))

    # Keycloak, cedar-agent, Vault -- richer pass/warn/fail semantics
    # (rfq_common.probe, ported from ops-dashboard, D4).
    #
    # Two real bugs found live (M8.3), both fixed here:
    # 1. ResourceServerSettings.oidc_issuer_url is deliberately the BARE
    #    base URL (provider-neutral field, see its own docstring) -- NOT
    #    the realm-scoped issuer a discovery document actually reports
    #    (http://keycloak:8080/.well-known/openid-configuration 404s;
    #    .../realms/rfq/.well-known/openid-configuration is the real path).
    # 2. Since M7's live-stack fix (KC_HOSTNAME), Keycloak reports a
    #    FIXED external issuer (https://keycloak.eaop-logistics.localhost/
    #    realms/rfq) regardless of which path reached it -- comparing
    #    against the INTERNAL DNS address used for actual token
    #    operations would warn on every real deployment, always, by
    #    design. Compare against the real external public issuer
    #    instead, same KEYCLOAK_ISSUER_URL convention ops-dashboard's
    #    config.py already uses for exactly this reason.
    keycloak_realm = os.environ.get("KEYCLOAK_REALM", "rfq")
    keycloak_public_issuer_url = os.environ.get(
        "KEYCLOAK_ISSUER_URL", f"https://keycloak.eaop-logistics.localhost/realms/{keycloak_realm}",
    )
    # verify=False: dev-only shortcut -- Caddy's local CA isn't in this
    # container's trust store (ops-dashboard solves this properly via
    # config.caddy_ca_bundle(); not pulled in here to avoid a
    # mission-control-api -> ops-dashboard dependency for one cert
    # bundle helper). Acceptable for this showcase's dev/local scope;
    # would need the same real CA-trust fix as any other service before
    # a non-dev deployment.
    results.append(probe_oidc_issuer("keycloak", keycloak_public_issuer_url, verify=False))
    results.append(probe_cedar("cedar-agent", os.environ.get("CEDAR_URL", "http://cedar-agent:8180")))
    results.append(probe_vault("vault", os.environ.get("VAULT_ADDR", "http://vault:8200")))

    statuses = [r.status for r in results]
    if "fail" in statuses:
        overall = "fail"
    elif "warn" in statuses:
        overall = "warn"
    else:
        overall = "pass"

    return {
        "status": overall,
        "checks": [r.model_dump() for r in results],
    }
