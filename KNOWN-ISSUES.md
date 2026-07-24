# Known issues

Bugs/limitations in **already-built, running code** — distinct from `TODO.md`
(missing design docs) and `build-plan.md` (phased work not started). Update this
file whenever a real component surfaces an issue that isn't fixed on the spot.

| # | Component | Issue | Severity | Status |
| - | --- | --- | --- | --- |
| 2 | `src/mock-fx` (`store.py`) | no case-normalization on currency pair — `/exchange-rates/cny/eur` 404s (fixtures are exact-case `"CNY/EUR"`) | low | open |
| 3 | `src/rfq_common` (`verify.py`) | `verify_with_jwks` tolerates a kid mismatch when the JWKS has exactly one key (test-fixture convenience) — weakens kid-pinning if reused unmodified against a real single-key dev IdP | medium | open — tighten before real IdP wiring |
| 4 | `src/mock-fx` (`cli.py`, tests) | reaches into `store._rates` (private) instead of a public accessor | cosmetic | open |
| 5 | `src/rfq_common` (`pdp/`) | resources are never loaded into Cedar `/v1/data` — correct today (no policy reads a resource attribute) but the first policy that needs one will silently fail until this is wired | latent | open — also tracked in `TODO.md` |
| 6 | `src/mock-fx` (`api.py`) | no CORS configured — irrelevant until a browser frontend calls it directly (Phase 5) | low | deferred |

## Fixed

| # | Component | Issue | Fixed in |
| - | --- | --- | --- |
| F1 | `src/mock-fx` | malformed `effectiveAt` query param → unhandled `ValueError` → 500 instead of 400 | commit `ab20e27` |
| F2 | `authorization/policies.cedar` | `capacity.check`/`lane.evaluate` had no policy → wrongly default-denied (D10/D11) | commit `094f457` |
| F3 | `authorization/policies.cedar` | `quote.submit-for-approval`'s clean case had no baseline permit → wrongly default-denied (D12) | commit `094f457` |
| F4 | `authorization/policies.cedar` | cedar-agent rejects `is` in policy scope | commit `094f457` |
| F5 | `src/rfq_common` (`app.py`) | non-ASCII banner text broke an HTTP header (latin-1-only) | commit `094f457` |
| F6 | `src/mock-fx` (`auth.py`) | hardcoded dev API key (`dev-fx-key`) as the default — nothing stopped deploying test/prod with it. Fixed via ADR-009: `rfq_common.secrets` (Vault-dev), `mock_fx.auth` now reads `FX_API_KEY` env or Vault, fails closed if neither is available. Proven live: `mock-fx serve` with `FX_API_KEY` unset, correct Vault-sourced key → 200, wrong/no key → 401. | this session |
| F7 | `identity/credentials-inventory.yaml` | `vault_path` values included the `secret/` KV-mount prefix, which `rfq_common.secrets.vault` also hardcodes → double `secret/secret/…`, 404 on every real Vault read (caught by the new live-integration tests) | this session |
| F8 | `src/mock-fx` | FX never consumed the masterdata source at all — no reference to it anywhere. Fixed: `FxStore` now validates every fixture currency via a **real masterdata API call** (`rfq_common.masterdata_client`), fails closed if masterdata is unreachable/unknown; new `/convert` endpoint uses masterdata's `minor_unit` for correct rounding (JPY caveat: `minor_unit=0`, not 2). Proven live and with a non-stubbed integration test suite. | this session |
