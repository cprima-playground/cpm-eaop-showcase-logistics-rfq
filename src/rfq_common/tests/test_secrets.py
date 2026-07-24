"""Offline-safe tests for rfq_common.secrets -- no Vault needed."""

from pathlib import Path

import pytest

from rfq_common.secrets import CredentialsInventory, SecretsClient

RFQ_ROOT = Path(__file__).resolve().parents[3]
INVENTORY_PATH = RFQ_ROOT / "identity" / "credentials-inventory.yaml"


def test_real_inventory_loads_and_validates():
    inv = CredentialsInventory.from_path(INVENTORY_PATH)
    assert len(inv.credentials) >= 5
    entry = inv.get("fx-api-key")
    assert entry.vault_path == "rfq/fx-api-key"
    assert "dev" in entry.environments


def test_inventory_unknown_name_raises():
    inv = CredentialsInventory.from_path(INVENTORY_PATH)
    with pytest.raises(KeyError):
        inv.get("does-not-exist")


def test_active_excludes_planned():
    inv = CredentialsInventory.from_path(INVENTORY_PATH)
    names = {c.name for c in inv.active()}
    assert "fx-api-key" in names
    assert "crm-mcp-api-key" not in names  # status: planned


def test_secrets_client_rejects_unknown_env():
    with pytest.raises(ValueError):
        SecretsClient("staging", inventory_path=INVENTORY_PATH)


def test_secrets_client_unknown_credential_raises():
    client = SecretsClient("dev", inventory_path=INVENTORY_PATH)
    with pytest.raises(KeyError):
        client.get("does-not-exist")


def test_secrets_client_test_env_is_target_not_implemented():
    client = SecretsClient("test", inventory_path=INVENTORY_PATH)
    with pytest.raises(NotImplementedError, match="Secret Manager"):
        client.get("fx-api-key")


def test_secrets_client_prod_env_is_target_not_implemented():
    client = SecretsClient("prod", inventory_path=INVENTORY_PATH)
    with pytest.raises(NotImplementedError):
        client.get("fx-api-key")
