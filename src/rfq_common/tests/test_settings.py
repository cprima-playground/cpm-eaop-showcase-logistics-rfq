"""M5.5: rfq_common.settings -- composable settings classes. Verifies the
alias-fallback behavior (new canonical env name wins, existing legacy
name still works) and the secret-resolution fallback (env override,
else Vault via SecretsClient) without touching any real network."""

from __future__ import annotations

from pathlib import Path

import pytest

from rfq_common.settings import (
    A2AClientSettings,
    CedarSettings,
    CredentialUnavailableError,
    PrincipalCredentialSettings,
    ResourceServerSettings,
    ServiceSettings,
    env,
)

RFQ_ROOT = Path(__file__).resolve().parents[3]
INVENTORY_PATH = RFQ_ROOT / "identity" / "credentials-inventory.yaml"


def test_env_prefers_first_set_name(monkeypatch):
    monkeypatch.delenv("SERVICE_HOST", raising=False)
    monkeypatch.setenv("A2A_HOST", "legacy-value")
    assert env("SERVICE_HOST", "A2A_HOST", default="fallback") == "legacy-value"

    monkeypatch.setenv("SERVICE_HOST", "canonical-value")
    assert env("SERVICE_HOST", "A2A_HOST", default="fallback") == "canonical-value"


def test_env_falls_back_to_default_when_nothing_set(monkeypatch):
    monkeypatch.delenv("NEVER_SET_VAR", raising=False)
    assert env("NEVER_SET_VAR", default="fallback") == "fallback"


def test_service_settings_canonical_name_wins(monkeypatch):
    monkeypatch.delenv("A2A_HOST", raising=False)
    monkeypatch.delenv("A2A_PORT", raising=False)
    monkeypatch.delenv("SERVICE_PUBLIC_URL", raising=False)
    monkeypatch.setenv("SERVICE_HOST", "0.0.0.0")
    monkeypatch.setenv("SERVICE_PORT", "9100")
    settings = ServiceSettings.from_env(default_port=8000)
    assert settings.host == "0.0.0.0"
    assert settings.port == 9100
    assert settings.public_url == "http://0.0.0.0:9100"


def test_service_settings_legacy_a2a_names_still_work(monkeypatch):
    monkeypatch.delenv("SERVICE_HOST", raising=False)
    monkeypatch.delenv("SERVICE_PORT", raising=False)
    monkeypatch.delenv("SERVICE_PUBLIC_URL", raising=False)
    monkeypatch.setenv("A2A_HOST", "127.0.0.1")
    monkeypatch.setenv("A2A_PORT", "8204")
    monkeypatch.setenv("A2A_PUBLIC_HOST", "lane-evaluation-agent")
    settings = ServiceSettings.from_env(default_port=8000)
    assert settings.host == "127.0.0.1"
    assert settings.port == 8204
    assert settings.public_url == "http://lane-evaluation-agent:8204"


def test_service_settings_public_url_env_takes_priority(monkeypatch):
    monkeypatch.setenv("SERVICE_HOST", "0.0.0.0")
    monkeypatch.setenv("SERVICE_PORT", "8204")
    monkeypatch.setenv("SERVICE_PUBLIC_URL", "http://lane-evaluation-agent:8204")
    monkeypatch.setenv("A2A_PUBLIC_HOST", "should-be-ignored")
    settings = ServiceSettings.from_env(default_port=8000)
    assert settings.public_url == "http://lane-evaluation-agent:8204"


def test_service_settings_default_port_used_when_unset(monkeypatch):
    for name in ("SERVICE_HOST", "SERVICE_PORT", "A2A_HOST", "A2A_PORT", "SERVICE_PUBLIC_URL", "A2A_PUBLIC_HOST"):
        monkeypatch.delenv(name, raising=False)
    settings = ServiceSettings.from_env(default_port=8104)
    assert settings.port == 8104
    assert settings.host == "127.0.0.1"


def test_resource_server_settings_derives_introspection_url(monkeypatch):
    monkeypatch.delenv("KEYCLOAK_INTROSPECTION_URL", raising=False)
    monkeypatch.setenv("KEYCLOAK_BASE_URL", "http://keycloak:8080")
    monkeypatch.setenv("KEYCLOAK_REALM", "rfq")
    settings = ResourceServerSettings.from_env()
    assert settings.introspection_url == "http://keycloak:8080/realms/rfq/protocol/openid-connect/token/introspect"
    assert settings.token_endpoint == "http://keycloak:8080/realms/rfq/protocol/openid-connect/token"


def test_resource_server_settings_legacy_keycloak_url(monkeypatch):
    monkeypatch.delenv("KEYCLOAK_BASE_URL", raising=False)
    monkeypatch.setenv("KEYCLOAK_URL", "http://localhost:8081")
    settings = ResourceServerSettings.from_env()
    assert settings.oidc_issuer_url == "http://localhost:8081"


def test_resource_server_settings_oidc_issuer_url_wins_over_legacy_names(monkeypatch):
    """OIDC_ISSUER_URL is canonical -- same precedence convention as
    SERVICE_PORT/A2A_PORT: the new name wins when both are set, the legacy
    name still works alone (test above)."""
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://sts.windows.net/some-tenant/")
    monkeypatch.setenv("KEYCLOAK_BASE_URL", "http://keycloak:8080")
    monkeypatch.setenv("KEYCLOAK_URL", "http://localhost:8081")
    settings = ResourceServerSettings.from_env()
    assert settings.oidc_issuer_url == "https://sts.windows.net/some-tenant/"


def test_cedar_settings_default(monkeypatch):
    monkeypatch.delenv("CEDAR_URL", raising=False)
    settings = CedarSettings.from_env()
    assert settings.cedar_url == "http://localhost:8280"


def test_a2a_client_settings_defaults(monkeypatch):
    monkeypatch.delenv("A2A_REQUEST_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("A2A_TASK_TIMEOUT_SECONDS", raising=False)
    settings = A2AClientSettings.from_env()
    assert settings.request_timeout_seconds == 10.0
    assert settings.task_timeout_seconds == 30.0


def test_principal_credential_settings_env_override_wins(monkeypatch):
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "from-env")
    settings = PrincipalCredentialSettings.from_env(
        client_id="lane-evaluation-agent-svc",
        expected_canonical_id="agent.lane-evaluation",
        vault_secret_name="lane-evaluation-agent-client-secret",
        legacy_secret_env_names=("LANE_EVAL_AGENT_SECRET",),
        inventory_path=INVENTORY_PATH,
    )
    assert settings.client_secret.get_secret_value() == "from-env"
    assert settings.client_id == "lane-evaluation-agent-svc"
    assert settings.expected_canonical_id == "agent.lane-evaluation"


def test_principal_credential_settings_legacy_env_name_wins_over_vault(monkeypatch):
    monkeypatch.delenv("OIDC_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("LANE_EVAL_AGENT_SECRET", "from-legacy-env")
    settings = PrincipalCredentialSettings.from_env(
        client_id="lane-evaluation-agent-svc",
        expected_canonical_id="agent.lane-evaluation",
        vault_secret_name="lane-evaluation-agent-client-secret",
        legacy_secret_env_names=("LANE_EVAL_AGENT_SECRET",),
        inventory_path=INVENTORY_PATH,
    )
    assert settings.client_secret.get_secret_value() == "from-legacy-env"


def test_principal_credential_settings_raises_when_nothing_available(monkeypatch):
    monkeypatch.delenv("OIDC_CLIENT_SECRET", raising=False)
    with pytest.raises(CredentialUnavailableError):
        PrincipalCredentialSettings.from_env(
            client_id="nonexistent-svc",
            expected_canonical_id="agent.nonexistent",
            vault_secret_name="nonexistent-client-secret",
            inventory_path=INVENTORY_PATH,
        )


def test_secret_str_does_not_leak_in_repr(monkeypatch):
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "super-secret-value")
    settings = PrincipalCredentialSettings.from_env(
        client_id="x", expected_canonical_id="agent.x",
        vault_secret_name="unused", inventory_path=INVENTORY_PATH,
    )
    assert "super-secret-value" not in repr(settings)
    assert "super-secret-value" not in str(settings)
