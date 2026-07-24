# ADR-009 — Credential inventory + management

**Status:** accepted.
**Context:** credentials are scattered — an FX APIKEY default hardcoded in source
(`KNOWN-ISSUES.md` #1), Keycloak client secrets (dev), Entra/WIF (test/prod),
future MCP-server APIKEYs. No inventory of what exists, no consistent local
storage mechanism.

## Decision

Split the problem in two, on purpose:

1. **Inventory** (*what exists*) — a plain, **non-secret** manifest
   (`identity/credentials-inventory.yaml`): name · purpose · consumer(s) ·
   environment(s) · owner · rotation cadence. Checked into git. **Never a value.**
2. **Storage** (*how it's protected*), env-conditional, mirroring the existing
   dev/test/prod split (`deploy/environments.md`):

| Env | Mechanism |
| --- | --- |
| **dev** | **HashiCorp Vault, dev-server mode** (`infra/vault/docker-compose.yml`) — one more container, alongside `cedar-agent`/`keycloak` |
| **test / prod** | **GCP Secret Manager** (already decided) |

## Rationale

- **Matches the established pattern.** Every other cross-cutting concern in this
  showcase already splits dev-vs-test/prod by mechanism (SSO: Keycloak/Entra;
  agent identity: client-creds/WIF). Secrets get the same shape: Vault-dev ↔
  Secret Manager. One story, not a bespoke one-off for credentials.
- **Machine-readable at boot**, not human-lookup-only. Vault has an HTTP API
  (`hvac` client) every container can read from at startup — unlike a password
  manager (KeePassXC) or a decrypt-then-source encrypted file (SOPS+age), both of
  which require extra per-container wiring and, worse, a private key/master
  password to distribute across every consumer.
- **Zero-cost, zero setup** — `vault server -dev` auto-unseals, needs no init
  ceremony; fits `deploy/environments.md`'s "dev is zero-cost, all local" rule.
- **Teaches the real pattern** — consistent with this showcase's existing taste
  for real infra locally (Keycloak, Caddy, cedar-agent), not toy stand-ins.

## Alternatives rejected

- **Encrypted file (SOPS + age)** — solid, but needs a decrypt-to-env step wired
  into every container/CLI and a private key distributed out of band. No runtime
  API for dynamic lookups.
- **KeePassXC** — human-centric (GUI/CLI lookup), not naturally consumable by six
  containers at startup without extra scripting; awkward multi-consumer story.

## Consequences

- `rfq_common` gains a `secrets` module: a thin Vault client in dev
  (`hvac`-backed), a Secret Manager client in test/prod, same interface —
  mirrors the `pdp` module's admin/runtime client split.
- `infra/vault/` holds the dev Vault compose + a seed script populating it from
  `identity/credentials-inventory.yaml`'s declared names (values generated locally,
  never committed).
- `KNOWN-ISSUES.md` #1 (hardcoded FX dev key) gets its real fix here: the key
  moves into Vault, `FX_API_KEY` is read at boot, no default baked into source.
