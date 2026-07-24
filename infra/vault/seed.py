"""Seed the dev Vault from identity/credentials-inventory.yaml (ADR-009).

For every ACTIVE credential with a vault_path, generates a fresh random value and
writes it. Idempotent (overwrite-on-rerun) -- dev secrets don't need the NOW/SEED
determinism contract (RUNNING.md); randomness here is correct, not a violation.
Prints names only, never values.

Run: uv run seed.py   (after `docker compose up -d`)
"""

from __future__ import annotations

import secrets as pysecrets
from pathlib import Path

from rfq_common.secrets import CredentialsInventory, VaultAdmin

RFQ_ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = RFQ_ROOT / "identity" / "credentials-inventory.yaml"


def main() -> int:
    inventory = CredentialsInventory.from_path(INVENTORY_PATH)
    admin = VaultAdmin()

    seeded = 0
    for entry in inventory.active():
        if entry.vault_path is None:
            continue
        if not entry.seed:
            print(f"skipped (seed: false, set manually): {entry.name}")
            continue
        value = pysecrets.token_urlsafe(32)
        admin.put(entry.vault_path, {"value": value})
        print(f"seeded: {entry.name} -> {entry.vault_path}")
        seeded += 1

    print(f"\n{seeded} credential(s) seeded into Vault (values never printed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
