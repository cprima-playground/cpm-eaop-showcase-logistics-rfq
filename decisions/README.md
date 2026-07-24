# Architecture Decisions (ADRs)

Ratified "we will…" decisions for the showcase, each with alternatives + rationale.
Distinct from `../business/decisions.md` (that logs *authorization* decisions D1–D9).

| ADR | Decision | Status |
| --- | --- | --- |
| [ADR-001](ADR-001-agentic-rfq-scope.md) | Agentic RFQ scope (repricing subprocess) | accepted |
| [ADR-002](ADR-002-sor-boundaries.md) | System-of-record boundaries | accepted |
| [ADR-003](ADR-003-agent-tool-boundaries.md) | Agent + tool boundaries | accepted |
| [ADR-004](ADR-004-authorization-model.md) | Authorization model (Cedar · projection · obligations) | accepted |
| [ADR-005](ADR-005-human-approval-boundaries.md) | Human-approval boundaries (HITL = quote status) | accepted |
| [ADR-006](ADR-006-tech-stack.md) | Standardize the mock-system tech stack | accepted |
| [ADR-007](ADR-007-theming.md) | Passable theming (design tokens → CSS vars) | accepted |
| [ADR-008](ADR-008-agent-runtime.md) | Agent runtime: Vertex Agent Engine (ADK); container in dev | accepted |
| [ADR-009](ADR-009-credential-management.md) | Credential inventory + management: Vault-dev / Secret Manager | accepted |
| [ADR-010](ADR-010-masterdata-source.md) | Masterdata source (Party/Location/Currency/... — 9 domains), reconciled with ADR-002 | accepted |

All eight accepted. 001–005 formalize the domain decisions; 006–008 the build/run decisions.
