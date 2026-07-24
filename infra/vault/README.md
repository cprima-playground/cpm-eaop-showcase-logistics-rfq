# Vault (dev) — local secrets store

ADR-009. Dev-only mechanism; test/prod use GCP Secret Manager (`deploy/environments.md`).

## Run it

```sh
docker compose up -d                          # rfq-showcase-vault on :8200
export VAULT_ADDR=http://localhost:8200
export VAULT_TOKEN=rfq-dev-root               # dev-mode fixed root token, never real
uv run seed.py                                # writes dev values for every
                                               # credentials-inventory.yaml entry with a vault_path
```

`seed.py` (planned, mirrors `rfq_common.pdp.bootstrap`'s shape) reads
`../../identity/credentials-inventory.yaml`, generates a fresh random value per
`vault_path` (or reads one from a local, gitignored `seed-overrides.env` if you
need a stable value), and writes it to Vault's KV engine. **Never commits a
value** — only the inventory (names) is version-controlled.

## Consuming a secret

`rfq_common.secrets` (planned) — a thin client mirroring `rfq_common.pdp`'s
admin/runtime split: `get(name) -> str`, resolving `vault_path` in dev,
`secret_manager_id` in test/prod. Until that lands, read directly:

```sh
curl -H "X-Vault-Token: $VAULT_TOKEN" http://localhost:8200/v1/secret/data/rfq/fx-api-key
```

## Why dev-mode is fine here, and only here

Dev-server mode is in-memory (lost on restart — fine, `reset`/`seed.py` regenerate
it) and uses a fixed root token. **Never point a real environment at a dev-mode
Vault.** test/prod use Secret Manager instead, precisely to avoid this trap.
