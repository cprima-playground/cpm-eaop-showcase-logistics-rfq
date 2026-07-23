# Approval / Workflow (mock)

**Owns:** ApprovalTask — the **task mechanism only**. **Interface:** `approval-mcp` (TARGET).

**Not** the system of record for the human decision. It surfaces the decision to a
human and triggers resumption; the authoritative decision is `Quote.status` in
`../cpq/`. See `../systems-of-record.yaml`.

Put here: interface contract, fixtures (an approval task carrying the evidence
package), and the mock spec.

- `contract.yaml` — create_approval_task · get_approval_status · record_recommendation · resume_route_decision
- `fixtures/` — an ApprovalTask with the triggered-thresholds evidence
- `mock-spec.md` — how a status change on the quote resumes the process
