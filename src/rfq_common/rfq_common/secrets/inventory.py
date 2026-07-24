"""Load + validate identity/credentials-inventory.yaml (ADR-009). The inventory
is WHAT credentials exist -- names only, never a value."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict


class CredentialEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    purpose: str
    consumers: list[str]
    environments: list[Literal["dev", "test", "prod"]]
    owner: str
    rotation: str
    vault_path: str | None = None
    secret_manager_id: str | None = None
    status: Literal["active", "planned"] = "active"
    seed: bool = True  # False for values seed.py must never randomize (e.g. a
    # secret that must match something generated elsewhere, like a Terraform
    # output) -- the inventory still declares the credential exists, seed.py
    # just skips writing a random value for it.


class CredentialsInventory(BaseModel):
    credentials: list[CredentialEntry]

    @classmethod
    def from_path(cls, path: str | Path) -> "CredentialsInventory":
        doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls.model_validate(doc)

    def get(self, name: str) -> CredentialEntry:
        for entry in self.credentials:
            if entry.name == name:
                return entry
        raise KeyError(f"no credential named {name!r} in the inventory")

    def active(self) -> list[CredentialEntry]:
        return [c for c in self.credentials if c.status == "active"]
