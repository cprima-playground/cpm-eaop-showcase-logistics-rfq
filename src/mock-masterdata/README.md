# mock-masterdata — the masterdata source, actually running

ADR-010. Serves 9 reference domains so other systems stop drifting their own
copies of Party/Location/Currency/etc: **reference by id/code, never embed**.
Built on `rfq_common` (same shape as `mock-fx`); one generic `CodeListStore`
(`rfq_common.codelist`) backs all 9 domains.

## Run it

```sh
uv run mock-masterdata serve --port 8003   # Swagger UI at http://localhost:8003/docs
uv run mock-masterdata domains             # list the 9 domains
uv run mock-masterdata list currencies
uv run mock-masterdata get locations CNSHA
uv run mock-masterdata reset
uv run pytest -v                           # 24 tests
```

```sh
curl -H "X-API-Key: $KEY" http://localhost:8003/locations/CNSHA
curl -H "X-API-Key: $KEY" http://localhost:8003/incoterms
```

The API key comes from `MASTERDATA_API_KEY` env or **Vault** (ADR-009) — no
hardcoded default, same discipline as `mock-fx`.

## The 9 domains

| Domain | Route | Real data seeded |
| --- | --- | --- |
| Party | `/parties` | Customer (ACME) + 5 carriers (COSCO, MAERSK, MSC, Lufthansa Cargo, Hapag-Lloyd) |
| Location | `/locations` | 15 real UN/LOCODE entries, migrated from `systems/tms/fixtures/locations.yaml` |
| Currency | `/currencies` | 7 real ISO 4217 codes |
| Incoterm | `/incoterms` | all 11 Incoterms® 2020 rules |
| Commodity | `/commodities` | 8 HS-code-level entries, 2 flagged dangerous-goods |
| Equipment | `/equipment` | standard container/vehicle types |
| Unit of Measure | `/units-of-measure` | KG/LB/CBM/CFT/PCS |
| Dangerous-goods class | `/dg-classes` | all 9 real IMDG classes |
| Payment term | `/payment-terms` | NET30/NET60/PREPAID/COD/LC |

Every route pair (`GET /{domain}` list, `GET /{domain}/{code}` get) is generated
from one table (`store.DOMAINS`) — adding a 10th domain needs no new route code.

## Result

Verified live: `uv run mock-masterdata serve`, unset `MASTERDATA_API_KEY`, fetched
the key from Vault, `curl`'d `/docs` (200), `/locations` with no key (401), and
`/locations/CNSHA`, `/incoterms` (11 entries), `/parties/ACME` with the Vault key
— all correct. 24/24 tests green.
