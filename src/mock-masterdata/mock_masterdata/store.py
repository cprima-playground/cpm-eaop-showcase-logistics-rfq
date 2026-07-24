"""The 9 masterdata domains (ADR-010), each a generic CodeListStore -- one
implementation, nine instances, instead of nine bespoke stores."""

from __future__ import annotations

import os
from pathlib import Path

from rfq_common.codelist import CodeListStore
from rfq_common.models import (
    Commodity,
    Currency,
    DangerousGoodsClass,
    Equipment,
    Incoterm,
    Location,
    Party,
    PaymentTerm,
    UnitOfMeasure,
)

RFQ_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURES_DIR = RFQ_ROOT / "systems" / "masterdata" / "fixtures"


def fixtures_dir() -> Path:
    return Path(os.environ.get("MASTERDATA_FIXTURES_DIR", str(DEFAULT_FIXTURES_DIR)))


# domain name -> (jsonl filename, model, code field)
DOMAINS = {
    "parties": ("parties.jsonl", Party, "party_id"),
    "locations": ("locations.jsonl", Location, "locode"),
    "currencies": ("currencies.jsonl", Currency, "code"),
    "incoterms": ("incoterms.jsonl", Incoterm, "code"),
    "commodities": ("commodities.jsonl", Commodity, "hs_code"),
    "equipment": ("equipment.jsonl", Equipment, "code"),
    "units-of-measure": ("units-of-measure.jsonl", UnitOfMeasure, "code"),
    "dg-classes": ("dg-classes.jsonl", DangerousGoodsClass, "class_code"),
    "payment-terms": ("payment-terms.jsonl", PaymentTerm, "code"),
}


class MasterdataStore:
    def __init__(self, base_dir: Path | None = None):
        self._base_dir = base_dir or fixtures_dir()
        self.stores: dict[str, CodeListStore] = {}
        self.reload()

    def reload(self) -> None:
        for domain, (fname, model, code_field) in DOMAINS.items():
            self.stores[domain] = CodeListStore(self._base_dir / fname, model, code_field=code_field)

    def list(self, domain: str):
        return self.stores[domain].list()

    def get(self, domain: str, code: str):
        return self.stores[domain].get(code)
