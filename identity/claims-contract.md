# Claim contract — repricing subprocess

Documents the IdP-agnostic claim contract this showcase assumes, **mirroring**
cpm-eaop `src/spike/model/identity.py` (`resolve_principal`). One contract, many
IdPs.

**First real (partial) implementation**: `rfq_common.identity.resolve_principal`
— built for `src/ops-dashboard/`'s human SSO login, proven against a real dev
Keycloak (`infra/keycloak/`). Deliberately narrower than the full contract
below: only the **human** path is implemented (`tid`/`oid`/`groups`/`roles` →
`Principal`); a non-human caller resolves to `kind="service"`, not `kind="agent"`
— the `azp`-vs-agent-registry branch isn't implemented (no agent authenticates
via SSO anywhere in RfQ; agents use client-credentials, a separate, already-proven
path). `department`/`business_unit` derivation from `groups.yaml` also isn't
implemented (that file doesn't exist yet — see `TODO.md`). Everything else below
remains contract-only, not yet coded.

## What `resolve_principal(claims)` consumes

| Claim (in) | Resolves to | Notes |
| --- | --- | --- |
| `scope` / `scp` | `scope` | space-separated string or list; Entra's `scp` renamed to `scope` by the adapter |
| `roles` | `roles` | humans only |
| `groups` | `member_of` (full list) | drives `department`/`business_unit` via group-path → cost_center |
| `tid` | `trust_domain` | present → `corporate`; MSA tenant → `consumer` |
| `active` | `active` | default `true`; inactive → deny (cross-cutting `forbid-inactive`) |
| `azp` | agent vs service | if `azp` ∈ agent registry (`agents/catalog.yaml` caller ids) → `kind=agent`, else `service` |
| `oid`, `department`, `business_unit` | pass-through / derived | department/BU derived from groups, not taken raw |

Everything else falls into a generic `attributes` bag (never a fixed field).

## Kind discrimination (same rule as cpm-eaop)

```text
tid / oid / groups present            -> human
else azp in agent registry            -> agent   (populates AgentIdentity)
else                                  -> service
```

## Entra adapter

The domain model is **Keycloak-native**; Entra needs a normalization layer
for the app-only path (mirrors cpm-eaop `src/spike/entra/principal.py`):
- `scp` → `scope`
- app-only detection (`idtyp == "app"`, or no `scp` and `sub == oid`) → surface `azp`
  so an app token classifies as `agent`/`service`, not `human`
- `tid == MSA` → `trust_domain = consumer`, else `corporate`

**`wids` merged into `roles` — verified WRONG against a real token, removed.**
Minted a real Entra v2.0 human token (`az login --use-device-code` against
`infra/entra/human-sso.tf`'s `ops-dashboard-web` app, real app-role
assignment via Microsoft Graph) and inspected it directly: app roles
already arrive under the claim name `roles`, identical to Keycloak's
shape (`"roles": ["ops-viewer"]`). `wids` (directory role-template IDs —
tenant-level roles like Global Administrator) never appeared on this
token at all; it's a different, Graph-audience-token-only concept, not
this app's roles. No merge needed — `resolve_principal`'s
`claims.get("roles")` already reads the right claim natively for both
providers. See `tmp/oidc-identity-unification-plan.md`'s "Implementation
findings" section for the full token shape.

`groups`: also read as-is (opaque `list[str]`) by both providers already —
Keycloak emits full group paths (`/rfq-commercial-emea`), Entra emits raw
group-object GUIDs. Neither is parsed into `department`/`business_unit`
today (that derivation isn't built yet, see above) — when it is, Entra's
side will need a GUID→name lookup (`infra/entra/`'s `group_object_ids`
Terraform output), not a path-string parse.

Keycloak needs no adapter — `resolve_principal` reads its claims natively.

## For this slice

The three agents authenticate as services with a `keycloak_client` in the registry
→ resolved to `kind=agent`. `mona.commercial` is a human (has `groups`/`tid`) with a
`route-deviation.approve` role and a delegated commercial limit read from her group.
