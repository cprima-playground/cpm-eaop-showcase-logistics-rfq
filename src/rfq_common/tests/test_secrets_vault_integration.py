"""Proves rfq_common.secrets works against a LIVE Vault (:8200). Skips (not
fails) if Vault isn't up -- same discipline as test_pdp_integration.py's
_sidecar_up() gate."""

from pathlib import Path

import pytest

from rfq_common.secrets import SecretsClient, VaultAdmin, VaultReader

RFQ_ROOT = Path(__file__).resolve().parents[3]
INVENTORY_PATH = RFQ_ROOT / "identity" / "credentials-inventory.yaml"
VAULT_URL = "http://localhost:8200"


@pytest.fixture(scope="module")
def vault_up():
    if not VaultReader(VAULT_URL).health():
        pytest.skip(f"Vault not running on {VAULT_URL} (docker compose up -d in infra/vault/)")
    return True


def test_write_then_read_round_trip(vault_up):
    VaultAdmin(VAULT_URL).put("rfq/test-round-trip", {"value": "hello-vault"})
    assert VaultReader(VAULT_URL).get("rfq/test-round-trip") == "hello-vault"


def test_secrets_client_reads_seeded_fx_key(vault_up):
    # simulate what seed.py does for fx-api-key, then read it back via the client
    VaultAdmin(VAULT_URL).put("rfq/fx-api-key", {"value": "test-seeded-fx-key"})
    client = SecretsClient("dev", inventory_path=INVENTORY_PATH, vault=VaultReader(VAULT_URL))
    assert client.get("fx-api-key") == "test-seeded-fx-key"


def test_secrets_client_caches_after_first_read(vault_up):
    VaultAdmin(VAULT_URL).put("rfq/fx-api-key", {"value": "value-a"})
    client = SecretsClient("dev", inventory_path=INVENTORY_PATH, vault=VaultReader(VAULT_URL))
    first = client.get("fx-api-key")
    VaultAdmin(VAULT_URL).put("rfq/fx-api-key", {"value": "value-b"})
    second = client.get("fx-api-key")  # cached -- still "value-a"
    assert first == second == "value-a"
