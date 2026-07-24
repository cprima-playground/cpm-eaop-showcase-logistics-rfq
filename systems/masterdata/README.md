# Masterdata Source (built)

**Owns:** Party · Location · Currency · Incoterm · Commodity · Equipment ·
UnitOfMeasure · DangerousGoodsClass · PaymentTerm. **Interface:** REST, APIKEY
only (no SSO, no MCP yet) — `src/mock-masterdata/`.

ADR-010: a different category from the other 6 systems — slow-changing,
enterprise-wide **reference** data, not a transactional object. Every other
system references these by id/code instead of embedding a copy (`customer_id`,
`carrier_id`, `locode`, currency code, …).

- `fixtures/` — the 9 real reference-data jsonl files (real UN/LOCODE, ISO 4217,
  Incoterms 2020, IMDG classes 1–9, …). See `../../decisions/ADR-010-masterdata-source.md`.
- Service: `../../src/mock-masterdata/README.md` — `uv run mock-masterdata serve`.
