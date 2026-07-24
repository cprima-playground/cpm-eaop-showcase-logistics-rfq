"""SecretsClient -- env-conditional facade (ADR-009): dev reads Vault, test/prod
would read GCP Secret Manager (TARGET -- no live GCP to exercise for real in this
environment; raises rather than pretending)."""

from __future__ import annotations

from pathlib import Path

from .inventory import CredentialsInventory
from .vault import VaultReader


class SecretsClient:
    def __init__(self, env: str, *, inventory_path: str | Path, vault: VaultReader | None = None):
        if env not in ("dev", "test", "prod"):
            raise ValueError(f"unknown environment: {env!r}")
        self._env = env
        self._inventory = CredentialsInventory.from_path(inventory_path)
        self._vault = vault or VaultReader()
        self._cache: dict[str, str] = {}

    def get(self, name: str) -> str:
        if name in self._cache:
            return self._cache[name]

        entry = self._inventory.get(name)  # raises KeyError if unknown
        if self._env != "dev":
            raise NotImplementedError(
                f"SecretsClient for env={self._env!r} is TARGET -- "
                f"credential {name!r} would come from GCP Secret Manager "
                f"(secret_manager_id={entry.secret_manager_id!r}); no live GCP "
                "in this environment to exercise for real."
            )
        if entry.vault_path is None:
            raise ValueError(f"credential {name!r} has no vault_path for dev")

        value = self._vault.get(entry.vault_path)
        self._cache[name] = value
        return value
