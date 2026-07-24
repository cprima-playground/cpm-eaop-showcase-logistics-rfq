"""Env + secrets resolution for the ops-dashboard -- same fail-closed pattern
as every other system's auth.py (ADR-009): env var if set, else Vault, else
raise. Session/OIDC config lives here, not scattered across sso.py/api.py."""

from __future__ import annotations

import os
import ssl
from pathlib import Path

from rfq_common.secrets import SecretsClient

RFQ_ROOT = Path(__file__).resolve().parents[3]
INVENTORY_PATH = RFQ_ROOT / "identity" / "credentials-inventory.yaml"

_cached_client_secret: str | None = None
_cached_session_secret: str | None = None


class CredentialUnavailableError(RuntimeError):
    pass


def keycloak_issuer_url() -> str:
    # keycloak.rfq-showcase.localhost over HTTPS (via infra/caddy), not the
    # bare :8081 port -- Keycloak derives its `iss` claim from whatever Host
    # header reached it (dev mode, no KC_HOSTNAME), so every caller must
    # agree on one hostname; HTTPS is required because Keycloak's session
    # cookies are Secure-flagged (dropped over plain HTTP for any
    # non-"localhost" host). Needs a hosts-file entry -- see infra/caddy/README.md.
    return os.environ.get("KEYCLOAK_ISSUER_URL", "https://keycloak.rfq-showcase.localhost/realms/rfq")


def keycloak_client_id() -> str:
    return os.environ.get("OPS_DASHBOARD_CLIENT_ID", "ops-dashboard-web")


def public_base_url() -> str:
    return os.environ.get("OPS_DASHBOARD_PUBLIC_URL", "http://localhost:8006")


def caddy_ca_bundle() -> str | None:
    """Path to Caddy's internal-CA root cert (infra/caddy/root.crt), extracted
    manually via `docker cp` -- see infra/caddy/README.md. Only needed when
    reaching Keycloak through the Caddy edge (its cert chains to this CA, not
    a publicly-trusted one); None (httpx's normal default) is correct for
    direct :8081 access."""
    env_value = os.environ.get("CADDY_CA_CERT")
    if env_value:
        return env_value
    default_path = RFQ_ROOT / "infra" / "caddy" / "root.crt"
    return str(default_path) if default_path.exists() else None


def caddy_ssl_context() -> ssl.SSLContext | bool:
    """httpx's `verify=<str path>` is deprecated in favor of an explicit
    SSLContext -- this builds one from caddy_ca_bundle(), or `True` (httpx's
    normal default) when there's no local CA to trust (direct :8081/:8006
    access, no Caddy in the loop)."""
    bundle = caddy_ca_bundle()
    return ssl.create_default_context(cafile=bundle) if bundle else True


def keycloak_client_secret() -> str:
    global _cached_client_secret
    if _cached_client_secret is not None:
        return _cached_client_secret

    env_value = os.environ.get("OPS_DASHBOARD_CLIENT_SECRET")
    if env_value:
        _cached_client_secret = env_value
        return _cached_client_secret

    try:
        _cached_client_secret = SecretsClient("dev", inventory_path=INVENTORY_PATH).get(
            "ops-dashboard-web-client-secret"
        )
        return _cached_client_secret
    except Exception as exc:
        raise CredentialUnavailableError(
            "ops-dashboard-web-client-secret is not available: OPS_DASHBOARD_CLIENT_SECRET "
            "is unset and Vault could not supply it (docker compose up -d in "
            "infra/vault/, terraform apply in infra/keycloak/terraform/, then write "
            "`terraform output ops_dashboard_web_client_secret` into Vault -- see "
            "infra/keycloak/README.md). Refusing to fall back to a known default."
        ) from exc


def session_secret() -> str:
    global _cached_session_secret
    if _cached_session_secret is not None:
        return _cached_session_secret

    env_value = os.environ.get("OPS_DASHBOARD_SESSION_SECRET")
    if env_value:
        _cached_session_secret = env_value
        return _cached_session_secret

    try:
        _cached_session_secret = SecretsClient("dev", inventory_path=INVENTORY_PATH).get(
            "ops-dashboard-session-secret"
        )
        return _cached_session_secret
    except Exception as exc:
        raise CredentialUnavailableError(
            "ops-dashboard-session-secret is not available: OPS_DASHBOARD_SESSION_SECRET "
            "is unset and Vault could not supply it (docker compose up -d in "
            "infra/vault/, then uv run seed.py). Refusing to fall back to a known default."
        ) from exc
