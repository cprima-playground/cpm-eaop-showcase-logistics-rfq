"""In-memory QMS store: Quote (aggregate) + an append-only QuoteVersion
history per quote. Baseline quotes reload from systems/qms/fixtures/quotes.yaml
at boot/reset, same convention as TMS/Rate/FX/masterdata -- but unlike those
(pure reference data, never mutated by a request), QMS also grows via real
POST /quotes + POST .../versions during a session; `reset()` discards that
growth back to the fixture baseline, exactly like TMS's route-availability
overlay resets.

customer_id is validated via a REAL masterdata API call at load/creation
(ADR-010: never a duplicated file) -- QMS's version of TMS's location check /
Rate's carrier+currency check.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from rfq_common.clock import now
from rfq_common.masterdata_client import MasterdataClient
from rfq_common.models import (
    CreateNextVersionRequest,
    CreateQuoteRequest,
    Quote,
    QuoteVersion,
    TimelineEntry,
)
from rfq_common.store_stats import collection_stats, combine_stats


class UnknownCustomerError(ValueError):
    pass


class UnknownQuoteError(ValueError):
    pass


class VersionConflictError(ValueError):
    pass


def _timestamp() -> str:
    return now().isoformat().replace("+00:00", "Z")


_ID_SUFFIX = re.compile(r"^Q-(\d+)$")


class QmsStore:
    def __init__(self, fixtures_dir: str | Path, masterdata_client: MasterdataClient | None = None):
        self._fixtures_dir = Path(fixtures_dir)
        self._masterdata = masterdata_client
        self._customer_cache: set[str] = set()
        self._quotes: dict[str, Quote] = {}
        self._versions: dict[str, list[QuoteVersion]] = {}
        self._next_id = 1001
        self.reload()

    def reload(self) -> None:
        """The admin `reset` -- back to the fixture baseline, discarding any
        quotes/versions created since boot."""
        self._quotes.clear()
        self._versions.clear()
        self._customer_cache.clear()
        self._next_id = 1001

        doc = yaml.safe_load((self._fixtures_dir / "quotes.yaml").read_text(encoding="utf-8"))
        for entry in doc.get("quotes", []):
            self._seed_quote(
                quote_id=entry["quote_id"], rfq_id=entry["rfq_id"],
                customer_id=entry["customer_id"], currency=entry["currency"],
            )
            m = _ID_SUFFIX.match(entry["quote_id"])
            if m:
                self._next_id = max(self._next_id, int(m.group(1)) + 1)

    def _validate_customer(self, customer_id: str) -> None:
        if self._masterdata is None or customer_id in self._customer_cache:
            return
        if not self._masterdata.exists("parties", customer_id):
            raise UnknownCustomerError(f"masterdata has no party for {customer_id!r}")
        self._customer_cache.add(customer_id)

    def _seed_quote(self, *, quote_id: str, rfq_id: str, customer_id: str, currency: str) -> QuoteVersion:
        self._validate_customer(customer_id)
        ts = _timestamp()
        version = QuoteVersion(quote_id=quote_id, version=1, status="draft", currency=currency, created_at=ts)
        quote = Quote(
            quote_id=quote_id, rfq_id=rfq_id, customer_id=customer_id,
            currency=currency, latest_version=1, latest_version_status="draft", created_at=ts,
        )
        self._quotes[quote_id] = quote
        self._versions[quote_id] = [version]
        return version

    def create_quote(self, req: CreateQuoteRequest, *, created_by: str | None = None) -> QuoteVersion:
        self._validate_customer(req.customer_id)
        quote_id = f"Q-{self._next_id}"
        self._next_id += 1
        version = self._seed_quote(
            quote_id=quote_id, rfq_id=req.rfq_id, customer_id=req.customer_id, currency=req.currency,
        )
        if created_by is not None:
            version = version.model_copy(update={"created_by": created_by})
            self._versions[quote_id] = [version]
        return version

    def get_quote(self, quote_id: str) -> Quote | None:
        return self._quotes.get(quote_id)

    def list_versions(self, quote_id: str) -> list[QuoteVersion]:
        return list(self._versions.get(quote_id, []))

    def get_version(self, quote_id: str, version: int) -> QuoteVersion | None:
        return next((v for v in self._versions.get(quote_id, []) if v.version == version), None)

    def create_next_version(self, quote_id: str, body: CreateNextVersionRequest) -> QuoteVersion:
        """D17 (quote.supersede) -- append, never mutate. expected_latest_version
        is the concurrency precondition (equivalent to If-Match): a mismatch is
        a lost race (409 via VersionConflictError), not an authorization failure."""
        versions = self._versions.get(quote_id)
        if versions is None:
            raise UnknownQuoteError(f"no quote {quote_id!r}")
        latest = versions[-1]
        if body.expected_latest_version != latest.version or body.prior_version != latest.version:
            raise VersionConflictError(
                f"stale precondition: latest version is {latest.version}, "
                f"got prior_version={body.prior_version} expected_latest_version={body.expected_latest_version}"
            )

        ts = _timestamp()
        new_version_num = latest.version + 1
        if body.copy_from_prior:
            carried = latest.model_dump(exclude={
                "version", "prior_version", "status", "created_at",
                "authorization_decision_ids", "pricing_rule_results", "trigger_event_ref",
            })
            new_version = QuoteVersion(
                **carried, version=new_version_num, prior_version=latest.version,
                status="draft", created_at=ts, trigger_event_ref=body.trigger_event_ref,
            )
        else:
            new_version = QuoteVersion(
                quote_id=quote_id, version=new_version_num, prior_version=latest.version,
                status="draft", currency=latest.currency, created_at=ts,
                trigger_event_ref=body.trigger_event_ref,
            )
        versions.append(new_version)
        self._quotes[quote_id] = self._quotes[quote_id].model_copy(
            update={"latest_version": new_version_num, "latest_version_status": "draft"}
        )
        return new_version

    def search(self, *, customer_id: str | None = None, rfq_id: str | None = None, status: str | None = None) -> list[Quote]:
        results = list(self._quotes.values())
        if customer_id is not None:
            results = [q for q in results if q.customer_id == customer_id]
        if rfq_id is not None:
            results = [q for q in results if q.rfq_id == rfq_id]
        if status is not None:
            results = [q for q in results if q.latest_version_status == status]
        return results

    def timeline(self, quote_id: str) -> list[TimelineEntry]:
        return [
            TimelineEntry(version=v.version, status=v.status, occurred_at=v.created_at or "")
            for v in self.list_versions(quote_id)
        ]

    def stats(self) -> dict:
        all_versions = [v for versions in self._versions.values() for v in versions]
        return combine_stats(
            collection_stats(list(self._quotes.values())),
            collection_stats(all_versions),
        )
