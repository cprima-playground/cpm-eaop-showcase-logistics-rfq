# Plan: Unify identity-provider verification (Keycloak/Entra) — deployment ≠ identity

**Revision 3** — rev 2 incorporated OIDC discovery instead of a
Keycloak-shaped JWKS default, a `TokenVerifier` protocol instead of a mode
string, `wids→roles` demoted to "verify against a real token before
implementing," equivalence tested at the `ResolvedPrincipal`/authorization
level not raw claims, one compose override file instead of two, and the
"Scenario B already works" claim narrowed to what's actually proven.

Rev 3 adds, per second review round: JWKS key-rotation refresh (turns out
already solved by existing code — `rfq_common.verify.verify()` uses
PyJWT's `PyJWKClient(cache_keys=True)`, which refreshes on an unknown
`kid` automatically; `JwtTokenVerifier` should call that function, not the
offline `fetch_jwks()`+`verify_with_jwks()` pair rev 2 drafted, which
would NOT have refreshed); a centralized `build_token_verifier()` factory
in `rfq_common` instead of 7 services each branching on verification mode;
`expected_audience` investigated for making-required, but a real minted
Keycloak token was checked first — `aud` is literally `"account"`
(Keycloak's client_credentials default; no service has an audience mapper
configured), so forcing a required per-resource value would break every
live call immediately. Kept optional, documented as a separate,
explicitly-flagged follow-up (provision audience mappers first); and
`_client_id_maps()` keyed by `(provider, client_id)` instead of bare
`client_id`, with loud failure on collision.

## Context

User's target matrix: **deployment environment (local/test/prod) and
identity environment (Keycloak/Entra-test/Entra-prod) are independent
axes** — e.g. local dev should be able to run against either local
Keycloak or the real test Entra tenant, without that meaning "local is now
a test deployment." Investigated whether the codebase already supports
this (a lot of it does — this was a documented, partially-built intent,
not a green-field ask):

- `deploy/environments.md` already states dev=Keycloak, test/prod=Entra,
  and "the claim contract makes Keycloak↔Entra a config swap, not a code
  change."
- `infra/entra/` (`main.tf`, `outputs.tf`) is real, applied Terraform — a
  live Entra tenant with human users/groups AND machine-identity
  applications (`machine_identity_client_ids`/`_client_secrets` outputs),
  not a stub.
- `rfq_common/verify.py` (JWKS-based) already takes `jwks_uri`/`issuer`/
  `audience` as plain params — no Keycloak-specific assumptions in the
  verification math itself. This is what `ops_dashboard/sso.py` and
  `mock_qms/sso.py` use for human SSO **token verification** today.
  **Narrowed claim (was overstated in rev 1)**: this proves *token
  verification* is issuer-agnostic already — it does NOT prove interactive
  Entra login works end-to-end. The browser-redirect / authorization-code
  / token-exchange flow for Entra is separate, not-yet-built plumbing
  (`sso.py`'s redirect construction is Keycloak-shaped today). Scenario B
  (local containers + test Entra) is proven for machine/workload auth by
  this plan; human interactive login against Entra remains future work,
  stated explicitly in "out of scope" below, not implied as already done.
- `rfq_common/pep/resolve.py`'s `resolve_principal()` already derives
  `provider: Literal["keycloak","entra"]` from the token's `iss` claim
  (`_provider_from_issuer()`), and classifies human/agent/workload via
  `azp` lookups that are provider-agnostic in *mechanism* — they just only
  currently read `identity/projections/keycloak.yaml` for the client-id
  map, not an Entra equivalent.

**The actual gap, found by reading `rfq_common/mcp_auth/verify.py`
directly**: MCP-server/agent-to-agent authentication
(`authenticate_request()`) verifies bearer tokens via **RFC 7662 token
introspection against Keycloak** — a POST to an introspection endpoint
with Basic auth. Microsoft's identity platform (Entra v2) does not expose
a standard RFC 7662 introspection endpoint for confidential-client apps —
this mechanism structurally cannot "just swap" to Entra via an env var,
unlike the JWKS path human SSO already uses for verification. This is the
part that actually blocks the user's Scenario B for anything MCP/agent-shaped.

Secondary, lower-risk gaps found: `ResourceServerSettings`
(`rfq_common/settings.py:83-104`) names everything `keycloak_*`
(`keycloak_base_url`, `keycloak_realm`) and its `token_endpoint`/
introspection-URL construction assumes Keycloak's `/realms/{realm}/...`
path shape; `agents/catalog.yaml`'s registry schema has a field literally
named `caller_identity.keycloak_client`; every one of 7 services'
`settings.py` has a function literally named `keycloak_url()`.

## Decision

**1. OIDC discovery, not a Keycloak-shaped JWKS default** (new module,
e.g. `rfq_common/oidc_discovery.py`)

Rejected (per review) the rev-1 idea of defaulting `jwks_uri` to
Keycloak's `/protocol/openid-connect/certs` shape when unset — that keeps
the "generic" abstraction secretly Keycloak-aware. Instead:

```python
class OidcMetadata(BaseModel):
    issuer: str
    jwks_uri: str
    token_endpoint: str
    authorization_endpoint: str | None = None

def discover_oidc_metadata(issuer: str, *, timeout: float = 5.0) -> OidcMetadata:
    """GET {issuer}/.well-known/openid-configuration -- both Keycloak and
    Entra publish this. Cached per-issuer (module-level dict), same
    once-per-process-lifetime caching rfq_common.verify's fetch_jwks
    already does for the JWKS document itself."""
```
Both providers support standard OIDC discovery — this removes the need for
any provider-shape branching in `settings.py` entirely. `OIDC_JWKS_URI`/
`OIDC_TOKEN_ENDPOINT` remain as optional explicit env-var overrides (escape
hatch for offline tests or a non-discoverable issuer), but are no longer
the primary mechanism.

**Caching**: the discovery *document* (which URL is the JWKS endpoint) is
cached per-issuer for the process lifetime — those URLs are stable,
provider-side changes to them are rare and operationally announced, not
silent. Add `refresh_oidc_metadata(issuer)` (clears the one cache entry)
as a manual escape hatch for that rare case, rather than a TTL — simpler,
and matches how `rfq_common.verify`'s own JWKS client caching already
works (see Decision 2: the *keys themselves* are what actually rotates
routinely, and that's handled separately, automatically, by existing code).

**2. `TokenVerifier` protocol + one shared factory, not a mode string
duplicated 7 times** (`rfq_common/mcp_auth/verify.py`)

Rejected (per review) threading `verification_mode`/`jwks_uri`/`issuer` as
loose kwargs through `authenticate_request()`. Also rejected (per second
review round) letting each of the 7 services independently branch on
`if mode == "jwks": ... elif mode == "introspection": ...` — that
duplicates the decision 7 times and is exactly the kind of drift this
plan exists to remove. One factory, in `rfq_common`, used by all 7:

```python
class TokenVerifier(Protocol):
    def verify(self, token: str, *, expected_audience: str | None = None) -> dict: ...
    # REVISED during implementation: minted a real client-credentials token
    # from the live Keycloak realm to check before hardcoding a requirement
    # -- its `aud` claim is literally "account" (Keycloak's client_credentials
    # default), not the calling resource server's client_id. NO service's
    # Keycloak client currently has an audience mapper configured. Forcing
    # `expected_audience: str` (required) would make every real token fail
    # verification immediately -- this isn't a "make the type stricter"
    # change, it's a "provision audience mappers in
    # infra/keycloak/terraform first" change, unscoped here. Kept Optional,
    # but every call site now passes it explicitly as `None` (see below)
    # instead of omitting the kwarg -- the gap stays visible in the code
    # that calls this, not silently absent. Real audience enforcement is a
    # separate, explicitly flagged follow-up (provision audience mappers +
    # THEN tighten this signature), not bundled into this pass.

class JwtTokenVerifier:
    """Thin wrapper over rfq_common.verify.verify() -- NOT the offline
    fetch_jwks()+verify_with_jwks() pair (that combo has no key-rotation
    refresh). rfq_common.verify.verify() uses PyJWT's PyJWKClient
    (cache_keys=True), which already refreshes automatically on an unknown
    `kid` -- reusing it here means key rotation is handled for free,
    not reimplemented."""
    def __init__(self, *, issuer: str, jwks_uri: str, timeout: float = 5.0):
        self._issuer, self._jwks_uri, self._timeout = issuer, jwks_uri, timeout

    def verify(self, token: str, *, expected_audience: str | None = None) -> dict:
        from rfq_common.verify import verify as verify_jwks
        return verify_jwks(token, jwks_uri=self._jwks_uri, issuer=self._issuer, audience=expected_audience).claims
        # NOTE: rfq_common.verify.verify()'s `audience` param needs widening
        # from `str` (required) to `str | None = None` alongside this change
        # -- PyJWT's jwt.decode() already treats audience=None as "skip aud
        # validation" internally, this is just relaxing the type hint to
        # match, not new decode logic.

class IntrospectionTokenVerifier:
    """Existing RFC 7662 mechanism, wrapped unchanged -- kept, not deleted,
    for Keycloak-only deployments that specifically want live-revocation
    checking (a real property JWKS-only verification doesn't give you)."""
    def __init__(self, *, introspection_endpoint: str, client_id: str, client_secret: str): ...
    def verify(self, token: str, *, expected_audience: str | None = None) -> dict: ...


def build_token_verifier(settings: ResourceServerSettings, *, mode: str) -> TokenVerifier:
    """The ONE place that decides jwks-vs-introspection and constructs the
    right object -- discovery happens here (explicit, separate step) before
    construction, per review: configuration/discovery stays apart from the
    cryptographic verifier itself, which stays a dumb wrapper."""
    if mode == "introspection":
        return IntrospectionTokenVerifier(
            introspection_endpoint=settings.introspection_url,
            client_id=..., client_secret=...,
        )
    metadata = discover_oidc_metadata(settings.oidc_issuer_url)
    return JwtTokenVerifier(issuer=metadata.issuer, jwks_uri=metadata.jwks_uri)


def authenticate_request(authorization: str | None, *, verifier: TokenVerifier, expected_audience: str | None = None, root: Path | None = None):
    token = extract_bearer_token(authorization)
    claims = verifier.verify(token, expected_audience=expected_audience)
    return resolve_principal(claims, root=root)
```
Each service's `cli.py` calls `build_token_verifier(settings, mode=...)`
once at startup (reading `MCP_AUTH_VERIFICATION_MODE` there) and passes
the resulting `verifier` into whatever calls `authenticate_request()` per
request — no service re-implements the jwks-vs-introspection choice.

**3. Provider-neutral registry field + Entra client-id projection**
(unchanged from rev 1 — this part of the review had no objections)

`agents/catalog.yaml`: rename `caller_identity.keycloak_client` →
`caller_identity.oidc_client_id`. Update
`rfq_common/pep/resolve.py::_client_id_maps()`'s reader and the generator
scripts (`tools/identity/gen_keycloak.py`, `gen_entra.py`,
`gen_cedar_entities.py`, `validator.py`).

`_client_id_maps()` extended to merge a second source when present:
`identity/projections/entra.yaml` (new — same shape as
`identity/projections/keycloak.yaml`, sourced from `infra/entra/`'s
`machine_identity_client_ids` output via a new
`tools/identity/write_entra_projection.py`, mirroring
`write_keycloak_tfvars.py`'s generator shape).

**Collision-safe lookup, per review**: client IDs are not globally unique
across independent issuers — merging two providers' maps by bare
`client_id` risks a silent last-write-wins collision if (implausibly, but
possible) both happen to reuse the same string. Key by `(provider,
client_id)` instead:

```python
def _client_id_maps(root: Path) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], str]]:
    """(provider, client_id) -> canonical_id -- provider is part of the key
    because client IDs aren't unique across independent issuers."""
    agent_map: dict[tuple[str, str], str] = {}
    workload_map: dict[tuple[str, str], str] = {}
    for provider, path in [("keycloak", root / "identity/projections/keycloak.yaml"),
                            ("entra", root / "identity/projections/entra.yaml")]:
        if not path.exists():
            continue
        # ... populate agent_map[(provider, client_id)] / workload_map[(provider, client_id)] ...
        # fail loudly (raise, don't silently overwrite) if a (provider, client_id)
        # key would collide with a DIFFERENT canonical_id already in the map --
        # that's a real provisioning error, not something to paper over.
    return agent_map, workload_map

def resolve_principal(claims: dict, *, root: Path | None = None) -> ResolvedPrincipal:
    ...
    provider = _provider_from_issuer(claims.get("iss"))
    azp = claims.get("azp")
    key = (provider, azp)
    if key in agent_map: ...
    if key in workload_map: ...
```
`_provider_from_issuer()` already exists and runs first, so this is a
lookup-key change, not new classification logic.

**4. Human-path Entra claim adapter — verify before implementing**

Rev 1 proposed merging Entra's `wids` claim into `roles`. Review correctly
flags this as unverified and likely wrong: `wids` is Entra's *directory
role template IDs* (tenant-level roles like Global Administrator) — a
different concept from *application roles*, which Entra v2 tokens already
surface via a `roles` claim directly (the actual Keycloak-equivalent
concept). **Do not implement the `wids` merge speculatively.** Instead:

- Mint a real token against `infra/entra/`'s already-provisioned tenant
  (a human test user, or a machine-identity client-credentials token) and
  inspect its actual claim shape first.
- Only then write `normalize_entra_claims(claims) -> dict` (explicit,
  named function, not an inline merge) implementing whatever the real
  token shape actually requires — likely nothing beyond what
  `resolve_principal()` already reads (`roles` may already be correctly
  named), possibly nothing at all for the app-role case.
- Update `identity/claims-contract.md` to match reality afterward, since
  its current `wids→roles` line appears to be an unverified carry-over
  from the cpm-eaop spike, not something confirmed against a real Entra
  token in *this* repo.

**5. One compose identity-override file, not two** (`infra/compose.identity.entra-test.yaml`)

Rejected (per review) shipping a `compose.identity.keycloak.yaml` that
changes nothing — a no-op file for "symmetry" hides the real default
behind an extra layer instead of clarifying it. Keycloak stays the
implicit default (today's `compose.support.yaml`/`compose.showcase.yaml`
behavior, unchanged); only the Entra override is a real file.

Reduce per-service duplication (review's point) with a shared YAML anchor
inside the one override file, merged alongside the existing
`*vault-env`/`*keycloak-env` anchor pattern already in
`compose.showcase.yaml`:

```yaml
# infra/compose.identity.entra-test.yaml
x-entra-test-env: &entra-test-env
  OIDC_ISSUER_URL: https://login.microsoftonline.com/${ENTRA_TEST_TENANT_ID}/v2.0
  MCP_AUTH_VERIFICATION_MODE: jwks

services:
  mock-qms:
    environment: {<<: *entra-test-env}
  tms-mcp:
    environment: {<<: *entra-test-env}
  # ... same one-line merge per service, no repeated URL literals
```
`${ENTRA_TEST_TENANT_ID}` sourced from a local `.env`/`--env-file`
(uncommitted, matches how Vault-backed secrets already never get
hardcoded into compose). Run:
```
docker compose --env-file .env.identity.entra-test \
  -f infra/compose.support.yaml -f infra/compose.showcase.yaml \
  -f infra/compose.identity.entra-test.yaml --profile full up
```
Client secrets for each service's own Entra app registration still resolve
via the existing `PrincipalCredentialSettings`/Vault-fallback path,
reading a different Vault path once Entra secrets are seeded there
(one-time manual step, out of scope here, same posture as Keycloak's).

## Explicitly out of scope (this pass)

- Building a `RegistryServiceResolver`/dynamic runtime IdP-switching UI —
  the ask is config-file-selectable, not runtime-hot-swappable.
- **Interactive human-SSO login against Entra** (authorization-code
  redirect, callback, token exchange in `ops_dashboard/sso.py`/
  `mock_qms/sso.py`) — token *verification* is issuer-agnostic already;
  the login *flow* itself is separate, not-yet-built plumbing. Stated
  explicitly per review's correction — this plan does not claim Scenario B
  works for human login, only for machine/workload auth.
- Seeding real Entra client secrets into Vault for every service.
- Any change to Cedar policies/authorization logic — `provider`/`issuer`
  on `ResolvedPrincipal` remain audit-only fields, not consumed by any
  policy.

## Critical files

- `src/rfq_common/rfq_common/oidc_discovery.py` (new — `OidcMetadata`,
  `discover_oidc_metadata()`)
- `src/rfq_common/rfq_common/mcp_auth/verify.py` (`TokenVerifier` protocol,
  `JwtTokenVerifier` wrapping `rfq_common.verify.verify()` — not the
  offline `fetch_jwks`/`verify_with_jwks` pair, for kid-refresh —
  `IntrospectionTokenVerifier`, `build_token_verifier()` factory;
  `authenticate_request()` takes a `verifier` param + required
  `expected_audience`, not loose optional kwargs)
- `src/rfq_common/rfq_common/settings.py` (`ResourceServerSettings`:
  `oidc_issuer_url` canonical field, `OIDC_ISSUER_URL` env var falling back
  to `KEYCLOAK_BASE_URL`/`KEYCLOAK_URL`; no Keycloak-shaped JWKS default)
- `src/{tms-mcp,rate-mcp,qms-mcp,approval-mcp,lane-evaluation-agent,
  route-decision-agent,commercial-normalization-agent}/*/settings.py`
  (`keycloak_url()` → `oidc_issuer_url()`; construct the right
  `TokenVerifier` per `MCP_AUTH_VERIFICATION_MODE`)
- `src/rfq_common/rfq_common/pep/resolve.py` (`_client_id_maps()` reads
  `oidc_client_id`, merges `identity/projections/entra.yaml`)
- `src/rfq_common/rfq_common/identity.py` (`resolve_principal()`: Entra
  adapter added ONLY after verifying real token shape — see Decision 4)
- `agents/catalog.yaml` (field rename: `keycloak_client` →
  `oidc_client_id`)
- `tools/identity/gen_keycloak.py`, `gen_entra.py`, `gen_cedar_entities.py`,
  `validator.py` (renamed field reference)
- `identity/projections/entra.yaml` (new) +
  `tools/identity/write_entra_projection.py` (new)
- `infra/compose.identity.entra-test.yaml` (new — the only override file)

## Implementation findings (real token, not assumed)

Minted a real client-credentials token from `infra/entra/`'s already-
provisioned tenant for `tms-mcp-svc` and inspected it directly before
writing any classification code. Two things the plan's assumptions got
wrong, both fixed:

1. **`_provider_from_issuer()` didn't recognize this tenant's actual
   issuer.** The app registration (no `api { requested_access_token_version
   = 2 }` set) issues a **v1.0** token: `iss: https://sts.windows.net/{tenant}/`,
   `ver: "1.0"` — not the `login.microsoftonline.com/.../v2.0` shape
   assumed. Fixed by also matching `sts.windows.net`, rather than requiring
   every app registration to be reconfigured for v2 tokens just to be
   recognized.
2. **No `azp` claim at all.** v1.0 Entra tokens carry `appid` instead.
   Fixed `resolve_principal()` to read `claims.get("azp") or claims.get("appid")`.
   This also empirically confirms `identity/claims-contract.md`'s
   documented "app-only detection" concern (a real v1 app-only token
   carries `tid`/`oid` too, `oid == sub` — it WOULD misclassify as human if
   the azp/appid-based workload lookup didn't run first, which it does).

**Real end-to-end proof achieved**: the minted token resolves via
`resolve_principal()` to `kind='workload' id='workload.tms-mcp'
provider='entra'` — genuine machine/workload Scenario B, not a mocked
claim shape.

**Human-path Entra adapter — now verified, and it turns out not needed.**
Provisioned a real human-SSO app registration (`infra/entra/human-sso.tf`,
new — `ops-dashboard-web`, mirrors `infra/keycloak/terraform/keycloak-sso.tf`'s
shape: `group_membership_claims`, one app role `ops-viewer`, delegated
`user_impersonation` scope). ROPC (ownerless password grant) is blocked
tenant-wide by MFA enforcement (`AADSTS50079`/`AADSTS50076` — Microsoft's
Sept-2025 CLI MFA rollout, not a per-app setting, no config workaround);
got a real token instead via `az login --use-device-code` (interactive,
human-completed MFA), assigned the `ops-viewer` app role to the signed-in
test account via Microsoft Graph (`appRoleAssignments`), inspected the
resulting real v2.0 token directly:

```json
{"iss": "https://login.microsoftonline.com/<tenant>/v2.0", "ver": "2.0",
 "tid": "<tenant>", "oid": "778249dc-...", "groups": ["5405e007-..."],
 "roles": ["ops-viewer"], "scp": "user_impersonation"}
```

Two things this disproves/confirms, both load-bearing:

1. **`wids→roles` merge is not needed — the plan's Decision 4 hypothesis
   was wrong.** Entra v2 app-scoped tokens carry app roles under the
   claim name `roles` **natively** — identical to Keycloak's shape.
   `wids` (directory role-template IDs, e.g. Global Administrator) doesn't
   even appear on this token; it's a Graph-audience-token-only claim,
   unrelated to *application* roles. `rfq_common/identity.py::resolve_principal()`
   already reads `claims.get("roles") if is_human else None` — reused
   as-is, zero changes required. `identity/claims-contract.md`'s
   "`wids` merged into `roles`" line is the actual bug: an unverified
   carry-over from the cpm-eaop spike, now empirically wrong for this
   claim shape, corrected there rather than implemented here.
2. **`groups` is already opaque-string on both sides — no parsing exists
   to break.** Keycloak's mapper emits `/rfq-commercial-emea`-style full
   paths; Entra emits raw group-object GUIDs (`5405e007-218a-4545-b385-65fb9fc7b7bb`).
   Both `rfq_common/identity.py` and `rfq_common/pep/resolve.py` store
   `groups` as a raw `list[str]` today, no path-derivation logic reads
   into it (`identity/claims-contract.md` already documents
   department-from-groups as **not yet implemented for either provider**)
   — so the GUID-vs-path difference doesn't regress anything working
   today. Flagged for whenever that derivation *is* built: it will need a
   GUID→name lookup for Entra (`infra/entra/`'s `group_object_ids`
   Terraform output already has the mapping), not a string-path parse.

**Net result: item 4 requires no code change.** `resolve_principal()`
already classifies and resolves a real Entra human token correctly,
`roles`-based UI-gating included, with the code exactly as it stands
after this pass's other changes.

## Verification

- `uv run pytest` in `rfq_common` — add tests for `discover_oidc_metadata()`
  (mocked `.well-known` response), `build_token_verifier()` (returns the
  right concrete type for each `mode`), and `JwtTokenVerifier`/
  `IntrospectionTokenVerifier` each implementing the `TokenVerifier`
  protocol correctly (fake token → expected claims / expected
  `AuthenticationError`).
- Add a test for the `(provider, client_id)` collision case: two entries
  mapping to different canonical ids under the same key raises loudly at
  `_client_id_maps()` load time, not at first lookup.
- **Equivalence test, corrected per review**: do NOT assert JWKS and
  introspection produce identical raw claims (they legitimately can
  differ). Assert instead that both verifiers, given a real live-Keycloak
  token, resolve to the **same `ResolvedPrincipal`** via
  `resolve_principal()` (same `kind`/`id`/`groups` — the fields
  authorization actually reads) — proves the swap is behavior-preserving
  for what downstream code cares about, not for raw claim-dict equality.
- Manual, gated on Decision 4's real-token spike: mint a client-credentials
  token from `infra/entra/`'s provisioned test tenant for one MCP server's
  Entra app registration; confirm `JwtTokenVerifier` +
  `identity/projections/entra.yaml`'s mapping resolves it to the correct
  `workload.*` canonical id. This is the concrete proof for
  machine/workload Scenario B — not a claim about human login.
- Full `docker compose --profile full up` (no identity override file, i.e.
  today's Keycloak default) still boots clean — proves the
  rename/generalization pass didn't regress the existing, working path.
