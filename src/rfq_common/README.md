# rfq_common — Phase 1 foundation

The shared library every mock system (Phase 2+) builds on (ADR-006). Standalone uv
package; installable/editable by future system packages under a workspace, or via
`uv pip install -e ../rfq_common`.

## Run the tests

```sh
uv run pytest -v                                  # 33 tests, offline-safe
# PDP integration tests additionally need the isolated cedar-agent:
#   (cd ../../spikes/repricing/policy-evaluation && docker compose up -d)
```

## Modules

| Module | Provides | Tests |
| --- | --- | --- |
| `models` | Pydantic entities — `InternalPrincipal`, `RFQ`, `Quote`, `RouteOption`, `ExchangeRate`, `RouteRecommendation`, `ApprovalTask` (mirrors `business/domain-model.yaml` + `identity/claims-contract.md`) | `test_models_jsonl.py` |
| `jsonl` | generic jsonl read/load/write (cpm-eaop-style deterministic fixtures) | `test_models_jsonl.py` |
| `verify` | IdP-agnostic JWT/JWKS verification (issuer/audience/expiry/signature); offline-testable via `verify_with_jwks` | `test_verify.py` (real RSA keypair, no network) |
| `pdp` | `PDPClient`, `SchemaAdmin`/`PolicyAdmin`/`DataAdmin`, `PolicyBundle` (`@id`/`@obligations` parsing), `generate_schema`, entity `ref`/`uid`/`action_ref` — path/namespace-parameterized, reusable by any future system | `test_pdp_integration.py` (against the real showcase authorization files + the live isolated cedar-agent) |
| `theme` | `ThemePack` model + `load_theme` (THEME_PATH > THEME > `teaching`) + `render_css_vars` (ADR-007) | `test_theme.py` (validates the 3 real theme packs) |
| `clock` | `now()`/`age_seconds()` (pinned `NOW`), `seed()`/`seeded_rng()` (pinned `SEED=42`) — the determinism contract (`../../RUNNING.md`) | `test_clock_app_cli.py` |
| `app` | `create_app(name, system_id, theme_pack)` — base FastAPI: `/healthz`, `/_theme.css`, banner header | `test_clock_app_cli.py` |
| `cli` | `create_cli(name, version)` — base Typer: `whoami`, `version` | `test_clock_app_cli.py` |

## Phase 1 exit criterion — met

> schema PUTs into a local cedar-agent; one request evaluates to the expected
> decision; unit tests green with a mock PDP.

`test_pdp_integration.py` goes further than the stated bar: it generates the
schema from the **real** `authorization/authz-projection.yaml` + `business/actions.yaml`,
asserts it matches the **committed** `agentic.cedarschema` byte-for-byte, loads it
plus the real `policies.cedar` into the live isolated cedar-agent, and verifies
**5 real decisions** (not just one) — including a forbid-beats-permit and an
obligation-merge case — through `rfq_common`'s own `PDPClient`.

## Real bugs this build caught

- Non-ASCII text (banner's em dash) in an HTTP header — latin-1 only; fixed with
  percent-encoding (`app.py`).
- (Carried from the policy-evaluation spike this library formalizes: the missing
  D10/D11/D12 policies and the `is`-in-scope Cedar syntax rejection — see
  `../../spikes/repricing/policy-evaluation/README.md`.)
