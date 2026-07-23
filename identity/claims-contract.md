# Claim contract — repricing subprocess

Documents the IdP-agnostic claim contract this showcase assumes, **mirroring**
cpm-eaop `src/spike/model/identity.py` (`resolve_principal`). One contract, many
IdPs. No engine code is implemented here — this is the contract the mocks honor.

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
(mirrors cpm-eaop `src/spike/entra/principal.py`):
- `scp` → `scope`
- app-only detection (`idtyp == "app"`, or no `scp` and `sub == oid`) → surface `azp`
  so an app token classifies as `agent`/`service`, not `human`
- `wids` merged into `roles`
- `tid == MSA` → `trust_domain = consumer`, else `corporate`

Keycloak needs no adapter — `resolve_principal` reads its claims natively.

## For this slice

The three agents authenticate as services with a `keycloak_client` in the registry
→ resolved to `kind=agent`. `mona.commercial` is a human (has `groups`/`tid`) with a
`route-deviation.approve` role and a delegated commercial limit read from her group.
