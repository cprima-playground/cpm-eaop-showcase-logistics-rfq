# policy-evaluation — the Cedar decision layer, actually running

The spike-within-a-spike that proves the acceptance criteria for scenarios 01–04 +
failure injections against a **live, isolated cedar-agent** — not just asserted on
paper. Standalone (own port, own project, no shared code with cpm-eaop per ADR-001)
but mirrors cpm-eaop's `src/spike/model` shapes byte-for-byte.

## Run it

```sh
docker compose up -d          # rfq-showcase-cedar-agent on :8280 (NOT cpm-eaop's :8180)
uv run pytest -v              # bootstraps automatically, runs all 7 tests
```

`docker compose down` when done. The container name (`rfq-showcase-cedar-agent`)
and compose project (`rfq-showcase`) are prefixed so `docker ps` never confuses it
with cpm-eaop's own `cedar-agent-cedar-agent-1`.

## What's here

| File | Role |
| --- | --- |
| `generate_schema.py` | projection + actions → `../../../authorization/agentic.cedarschema` (generated, never hand-edited) |
| `entities.py` | Cedar entity refs; static principal/group data (resources need none — see docstring) |
| `bundle.py` | parses `policies.cedar` (`@id`/`@obligations`); obligation-id resolution |
| `bootstrap.py` | clears + loads schema/policies/data into the isolated instance |
| `kill_switch.py` | PEP-level pre-check (NOT a Cedar policy) — fails closed before Cedar is called |
| `scenario_runner.py` | drives a scenario `.yaml`'s `when` block through `/v1/is_authorized` |
| `test_scenarios.py` | the 7 tests — 4 scenarios + 3 failure injections |

## Result: decision supported

All 7 tests pass. Running this surfaced **3 real bugs in the authorization model**
that pure design review missed:

1. **D10/D11 missing** — scenarios 02/03 exercised `capacity.check`/`lane.evaluate`;
   neither had a policy, so both would have wrongly default-denied. Added two
   baseline permits.
2. **D12 missing** — `quote.submit-for-approval`'s "nothing is wrong" case (FX quiet,
   margin at/above floor) had only a forbid (D4b) and a below-floor permit (D5) — no
   baseline permit, so it default-denied. Added `submit-quote-when-within-thresholds`.
3. **`is` in policy scope rejected by cedar-agent** ("unexpected token `is`") — same
   issue cpm-eaop hit historically. Fixed by dropping all `principal is Type`/
   `resource is Type` scope clauses in favor of bare `principal`/`resource` (or
   `principal in Group`), matching cpm-eaop's actual working `policies.cedar`.
4. Scenario 01's `then` block predated D8/D9 and was stale (didn't account for the
   9.3% cost-variance obligation merging in) — fixed to match.

## Architecture consequence

Confirms the core hypothesis (`../README.md`): distinct threshold types compose
correctly (permit+obligation merging, forbid deny-precedence) on a real Cedar PDP.
Also confirms the "resources need no `/v1/data` entry" simplification empirically —
every policy here only reads `context.*`/`principal.*`, so only principals+groups
are loaded as data.

## Open questions carried forward

- Entity-data sync at request time (per cpm-eaop's known `cedar-agent` constraint)
  wasn't exercised — no *dynamic* resource attributes were needed here.
- Kill-switch is implemented as a local Python registry for this spike; the real
  design (`../../authorization/governance-policies.md`) wants it centrally checked
  before every governed edge (A2A, MCP, grant) — this proves the *shape* only.
