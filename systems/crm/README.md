# CRM (mock)

**Owns:** Customer · RFQ · ContractedLane. **Interface:** `crm-mcp` (TARGET).

Put here: interface contract (resources/tools it exposes), fixtures (customers, the
RFQ, the contracted lane), and the mock spec. See `../systems-of-record.yaml` and
`../../interfaces/mcp/tools.yaml`.

- `contract.yaml` — exposed resources/tools (→ domain actions)
- `fixtures/` — e.g. `RFQ-1001` customer + contracted lane
- `mock-spec.md` — what the spike's mock returns
