# Environments — dev · test · demo/prod

Three environments, one set of images. **12-factor: the same container runs
everywhere; only env config differs.** The claim contract
(`../identity/claims-contract.md`) makes **Keycloak ↔ Entra a config swap, not a code
change** — `resolve_principal` handles both, the Entra adapter normalizes claims.

| Aspect | **dev** | **test** | **demo / prod** |
| --- | --- | --- | --- |
| Purpose | build + local demo | validate on real cloud | stakeholder demo |
| Cost | **none** (all local) | personal GCP (your spend) | corporate GCP |
| Host | `docker compose` + Caddy | Cloud Run + Apigee | Cloud Run + Apigee |
| GCP project | — | **personal** | **corporate** |
| Human SSO | **Keycloak** (local) | **Entra ID** | **Entra ID** |
| Agent identity | Keycloak **client-credentials** | **WIF → Entra** (GCP SA federates) | **WIF → Entra** |
| Persistence | in-memory / SQLite | Firestore (free tier) or SQLite | Firestore |
| Edge / PEP | Caddy | Apigee | Apigee |
| Secrets | `.env` | Secret Manager | Secret Manager |
| Theme | `teaching` / `solarized-light` | `teaching` | corporate brand (`THEME_PATH`) |

## What actually changes between envs (just config)

```text
OIDC_ISSUER          Keycloak realm URL   →  Entra tenant
AGENT_IDENTITY_MODE  keycloak-client-creds →  wif-entra
CEDAR_AGENT_URL      cedar-agent:8180      →  private Cloud Run URL
PERSISTENCE          memory|sqlite         →  firestore
THEME / THEME_PATH   teaching|solarized    →  corporate pack
SECRETS              .env                  →  Secret Manager
EDGE                 Caddy                 →  Apigee
```

Same images; env files live in `../infra/env/<env>/` (non-secret) + Secret Manager
(secrets) on GCP.

## Agent identity per env (resolves ADR-006 §4)

- **dev:** Keycloak **client-credentials** — trivial locally, no cloud issuer needed.
- **test + prod:** **WIF → Entra** — the GCP service account's OIDC token federates to
  an Entra token via a federated credential (**no stored secret**). Matches cpm-eaop
  `hello-agent-gcp`. Entra is the IdP on GCP for both humans (SSO) and agents (WIF).

Either way the agent emits an `azp` the claim contract resolves to `kind=agent`.

## Promotion

```text
dev (local, Keycloak, free)
  → test (personal GCP, Entra, WIF)      # prove it on real cloud + real IdP
    → demo/prod (corporate GCP, Entra)   # stakeholder demo, corporate brand
```

Promotion = same images + the env config above. No rebuild for IdP or theme.

## Local substitutes — what can / can't run locally for free

The whole showcase runs locally for free via substitutes. **Apigee is the only
component with no free local equivalent** (Caddy is its local stand-in).

| Cloud component | Local substitute (free) |
| --- | --- |
| **Apigee** (edge / PEP) | **Caddy** — genuine substitution; Apigee can't run locally free |
| Entra ID | **Keycloak** (Entra basic is free-tier anyway) |
| Vertex Agent Engine | **ADK local runner** (+ stubbed LLM) |
| WIF | **Keycloak client-credentials** |
| Cloud Run | `docker compose` |
| Firestore | in-memory / SQLite / **Firestore emulator** |
| Secret Manager | `.env` |
| Cloud Logging | local JSON logs |

Cloud Run (warm instances), Vertex, and real Firestore bill only **when hosted** —
each has a free local path above.

## Cost discipline

- **dev:** zero — never touches GCP.
- **test:** your personal project; keep `min-instances=0` except while demoing;
  Firestore free tier; tear down after.
- **prod:** corporate; `min-instances=1` only during a scheduled demo → scale to zero after.
