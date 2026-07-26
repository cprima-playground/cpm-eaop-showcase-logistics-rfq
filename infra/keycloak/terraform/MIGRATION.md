> **Status: applied.** M3.2a: 3 in-place updates (region added, sam's
> manager corrected), 0 adds/destroys, verified zero-diff before and
> after via `moved` blocks. M3.2b: live 409 Conflict on first attempt —
> `aiden.ashford` was generated despite being RETAIN-classified below,
> colliding with his hand-authored resource on duplicate email. Fixed:
> `tools/identity/write_keycloak_tfvars.py` now excludes
> `RETAIN_USERNAMES` explicitly (regression-tested,
> `test_stage_b_excludes_retained_aiden`), not just documented here.
> Final state: 42 resources generator-owned, `terraform plan` clean.

# Keycloak Terraform migration manifest (M3.2, hybrid)

Split per review, not one mixed plan:

- **M3.2a — legacy canonical human/group migration.** Existing
  resources that already map 1:1 to `identity/actors.yaml`/`groups.yaml`
  take ownership under the generator. **Zero-diff required** before
  this stage is considered done.
- **M3.2b — new machine-principal provisioning.** 3 agent + 4 workload
  Keycloak clients — none exist in `.tf` today. **Expected-adds-only**
  plan, applied separately from M3.2a, never in the same `plan`/`apply`.

## `oid` investigation (required before classifying users)

Traced `oid` through `rfq_common.identity.resolve_principal()`
(`src/rfq_common/rfq_common/identity.py:21,40,47`): it's read as one of
three presence-checked keys (`tid`/`oid`/`groups`) to classify a caller
human-vs-service, then copied onto `Principal.oid` — **never read
again downstream** (no route/authz check/template references `.oid`;
confirmed by search). The stable subject identifier is `sub` →
`Principal.id`, not `oid`. `identity/claims-contract.md` confirms:
derived fields come from `groups`, not `oid`.

**Conclusion:** `oid` must still be *emitted* (classification needs its
presence) but its specific value is inert — the existing hand-assigned
GUIDs (`8e41c2b0-...-000000000011` etc.) carry no meaning worth
preserving byte-for-byte. `tools/identity/gen_keycloak.py` now
generates it deterministically (`uuid5`, not random) from the canonical
id — a provider-projection concern, not a canonical identity fact, so
it's generated at projection time, not stored in `identity/actors.yaml`.

## Classification (4 categories, not a flat old→new list)

| Resource | Classification | Disposition |
|---|---|---|
| `keycloak_user.diane_delgado` | Canonical, generator-owned | → `keycloak_user.humans["diane.delgado"]` |
| `keycloak_user.mona_commercial` | Canonical, generator-owned | → `keycloak_user.humans["mona.commercial"]` |
| `keycloak_user.sam_pricing` | Canonical, generator-owned | → `keycloak_user.humans["sam.pricing"]` |
| `keycloak_group.rfq_commercial_emea` | Canonical, generator-owned | → `keycloak_group.groups["rfq-commercial-emea"]` |
| `keycloak_group.rfq_pricing_emea` | Canonical, generator-owned | → `keycloak_group.groups["rfq-pricing-emea"]` |
| `keycloak_user_groups.mona_commercial_groups` | Canonical, generator-owned | → `keycloak_user_groups.human_group_memberships["mona.commercial"]` |
| `keycloak_user_groups.sam_pricing_groups` | Canonical, generator-owned | → `keycloak_user_groups.human_group_memberships["sam.pricing"]` |
| `keycloak_user.aiden_ashford` | **Ambiguous** | RETAIN — `identity/actors.yaml` has `aiden.ashford` (canonical), but his live group `rfq_qms_platform` isn't in `identity/groups.yaml`'s 9-group model and his `job_title_id: platform-administrator` has no `department_id` (deliberately, not a logistics role). Migrating the user without a group mapping the generator can't produce would silently drop his group membership. **Investigate in a future pass** — not this migration. |
| `keycloak_user.alice` | Existing, outside canonical model | RETAIN — ops-dashboard SSO test fixture, no `identity/actors.yaml` entry |
| `keycloak_user.bob` | Existing, outside canonical model | RETAIN — same as alice |
| `keycloak_group.ops_team` | Existing, outside canonical model | RETAIN — alice's group, not in `identity/groups.yaml` |
| `keycloak_group.rfq_qms_platform` | Existing, outside canonical model | RETAIN — aiden's group, see Ambiguous note above |
| `keycloak_openid_client.qms_web` | Existing, outside canonical model | RETAIN — application OIDC client, bespoke protocol mappers, not a machine-identity client the generator produces |
| `keycloak_openid_client.ops_dashboard_web` | Existing, outside canonical model | RETAIN — same reasoning |
| every `keycloak_role.*` / `ops_viewer` | Existing, outside canonical model | RETAIN — no `job_title/department → Keycloak role` projection rule exists; not inferring one |
| `keycloak_user_roles.{diane,mona,sam}_*_roles` | Existing, outside canonical model (reference update only) | RETAIN as resources; `user_id` argument updated to the new `keycloak_user.humans[...]` address (consequential edit, not a migration of the resource itself) |
| `keycloak_user_roles.{aiden,alice}_*_roles`, `keycloak_user_groups.{aiden,alice}_*_groups` | Existing, outside canonical model | RETAIN, untouched |
| `keycloak_realm.rfq`, `null_resource.enable_unmanaged_attributes` | Existing, outside canonical model | RETAIN, untouched |
| `workload.tms-mcp`/`rate-mcp`/`qms-mcp`/`approval-mcp` | New canonical principal | CREATE (M3.2b) |
| `agent.lane-evaluation`/`commercial-normalization`/`route-decision` service clients | New canonical principal | CREATE (M3.2b) — no existing Keycloak client for any of the 3 agents today, confirmed by search |
| 7 bench-depth/new-domain humans (APAC/AMER + nadia/felix/tariq/sofia) | New canonical principal | CREATE (M3.2b) |
| 6 new groups (`rfq-{commercial,pricing}-{apac,amer}`, `rfq-planning-{emea,apac,amer}`) | New canonical principal | CREATE (M3.2b) |

## Known limitation carried into the `for_each` model

A human is assumed to belong to at most one group
(`human_group_memberships` keyed by username). True for every migrated
human today — revisit the key scheme if that changes.

## Verification

M3.2a: `terraform plan` shows **zero changes**. M3.2b (separate
`plan`/`apply`): matches exactly the CREATE rows above, nothing else —
in particular, no diff on any RETAIN-classified resource.
