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
    DecisionRecord,
    PricingInputs,
    Quote,
    QuoteDecisionRequest,
    QuoteVersion,
    RouteRecommendationInput,
    RuleResult,
    TimelineEntry,
)
from rfq_common.store_stats import collection_stats, combine_stats

from . import pricing_policy
from .clients import FxClient, RateClient

# R2's threshold (qms-pricing-rules.md): fx_variance_pct_x10 > 20 (2.0%) is
# over threshold. R1/R2 are real (R1 via the versioned demo pricing_policy
# module -- see its own docstring for why it exists and what it isn't).
# R3/R4/R5 need a contracted-lane baseline route that isn't QMS-owned data
# (RFQ isn't QMS's -- see this module's own docstring) -- always
# "not_evaluated" with an honest reason, never a fabricated result.
_R2_THRESHOLD_PCT_X10 = 20
_NOT_EVALUATED_NO_BASELINE = "no contracted-lane baseline route stored on Quote -- RFQ isn't QMS-owned data, see store.py's module docstring"


class UnknownCustomerError(ValueError):
    pass


class UnknownQuoteError(ValueError):
    pass


class VersionConflictError(ValueError):
    pass


class InvalidStateError(ValueError):
    """A version isn't in the status this operation requires (e.g. pricing
    a version that's already priced, or submitting one that isn't)."""
    pass


class ComposeIncompleteError(ValueError):
    """POST .../price's own precondition: route-recommendation and
    pricing-inputs must be composed first (400, matches api.py's module
    docstring), or a referenced route/rate genuinely doesn't exist."""
    pass


def _timestamp() -> str:
    return now().isoformat().replace("+00:00", "Z")


_ID_SUFFIX = re.compile(r"^Q-(\d+)$")


class QmsStore:
    def __init__(
        self, fixtures_dir: str | Path, masterdata_client: MasterdataClient | None = None,
        *, fx_client: FxClient | None = None, rate_client: RateClient | None = None,
    ):
        self._fixtures_dir = Path(fixtures_dir)
        self._masterdata = masterdata_client
        self._fx = fx_client
        self._rate = rate_client
        self._customer_cache: set[str] = set()
        self._quotes: dict[str, Quote] = {}
        self._versions: dict[str, list[QuoteVersion]] = {}
        self._decisions: dict[str, list[DecisionRecord]] = {}
        self._next_id = 1001
        self.reload()

    def reload(self) -> None:
        """The admin `reset` -- back to the fixture baseline, discarding any
        quotes/versions created since boot."""
        self._quotes.clear()
        self._versions.clear()
        self._decisions.clear()
        self._customer_cache.clear()
        self._next_id = 1001

        doc = yaml.safe_load((self._fixtures_dir / "quotes.yaml").read_text(encoding="utf-8"))
        for entry in doc.get("quotes", []):
            self._seed_quote(
                quote_id=entry["quote_id"], rfq_id=entry["rfq_id"],
                customer_id=entry["customer_id"], currency=entry["currency"],
                versions=entry.get("versions", 1),
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

    def _seed_quote(self, *, quote_id: str, rfq_id: str, customer_id: str, currency: str, versions: int = 1) -> QuoteVersion:
        """`versions` > 1 seeds a real supersede chain (v1..vN, each with
        prior_version set) -- baseline fixtures can demonstrate the
        append-only history feature at rest, not just via live POSTs."""
        self._validate_customer(customer_id)
        ts = _timestamp()
        version_history = [
            QuoteVersion(
                quote_id=quote_id, version=v, prior_version=(v - 1) or None,
                status="draft", currency=currency, created_at=ts,
            )
            for v in range(1, versions + 1)
        ]
        quote = Quote(
            quote_id=quote_id, rfq_id=rfq_id, customer_id=customer_id,
            currency=currency, latest_version=versions, latest_version_status="draft", created_at=ts,
        )
        self._quotes[quote_id] = quote
        self._versions[quote_id] = version_history
        return version_history[0]

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
            # copy_from_prior means the COMPOSED draft inputs (recommendation_id,
            # selected_route_id, rate_refs, fx_rate_ref, ...) carry forward --
            # never the prior version's COMPUTED pricing outputs, which must
            # be re-derived by re-pricing this new draft, not inherited stale.
            carried = latest.model_dump(exclude={
                "version", "prior_version", "status", "created_at",
                "authorization_decision_ids", "pricing_rule_results", "trigger_event_ref",
                "total_cost_eur_cents", "proposed_sell_price_eur_cents", "pricing_policy_ref",
                "margin_pct_x10", "fx_variance_pct_x10", "fx_rate_snapshot",
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

    def _replace_version(self, quote_id: str, version: int, updated: QuoteVersion) -> None:
        versions = self._versions[quote_id]
        idx = next(i for i, v in enumerate(versions) if v.version == version)
        versions[idx] = updated
        if version == versions[-1].version:
            self._quotes[quote_id] = self._quotes[quote_id].model_copy(
                update={"latest_version_status": updated.status}
            )

    def _draft_version(self, quote_id: str, version: int) -> QuoteVersion:
        qv = self.get_version(quote_id, version)
        if qv is None:
            raise UnknownQuoteError(f"no version {version} for quote {quote_id!r}")
        if qv.status != "draft":
            raise InvalidStateError(f"version {version} of {quote_id!r} is {qv.status!r}, not draft")
        return qv

    def compose_route_recommendation(self, quote_id: str, version: int, body: RouteRecommendationInput) -> QuoteVersion:
        qv = self._draft_version(quote_id, version)
        updated = qv.model_copy(update={
            "recommendation_id": body.recommendation_id, "selected_route_id": body.selected_route_id,
        })
        self._replace_version(quote_id, version, updated)
        return updated

    def compose_pricing_inputs(self, quote_id: str, version: int, body: PricingInputs) -> QuoteVersion:
        qv = self._draft_version(quote_id, version)
        updated = qv.model_copy(update={
            "fx_rate_ref": body.fx_rate_ref, "rate_refs": list(body.rate_refs),
            "pricing_terms_ref": body.pricing_terms_ref, "margin_floor_ref": body.margin_floor_ref,
        })
        self._replace_version(quote_id, version, updated)
        return updated

    def price_version(self, quote_id: str, version: int) -> QuoteVersion:
        """The atomic command (D16): resolve real rate/FX facts, compute
        total cost, evaluate R2 (FX variance, real once a prior snapshot
        exists), derive a sell price + R1 via the versioned DEMO pricing
        policy (mock_qms/pricing_policy.py -- explicitly synthetic, not a
        decided commercial formula), and write draft -> priced. R3-R5 (need
        a contracted-lane baseline QMS doesn't store) stay `not_evaluated`
        with a real reason -- never silently omitted, never fabricated
        (see RuleResult's docstring)."""
        qv = self._draft_version(quote_id, version)
        if not (qv.recommendation_id and qv.selected_route_id and qv.rate_refs and qv.fx_rate_ref):
            raise ComposeIncompleteError(
                "route-recommendation and pricing-inputs must both be composed before pricing"
            )
        if self._rate is None or self._fx is None:
            raise ComposeIncompleteError("rate/fx services are not configured on this QMS instance")

        total_cost_eur_cents = 0
        fx_rate_used: float | None = None
        for route_id in qv.rate_refs:
            rate = self._rate.get_rate(route_id)
            if rate is None:
                raise ComposeIncompleteError(f"no rate on file for route {route_id!r}")
            amount_cents = rate["base_cost"] + rate["surcharges"]
            currency = rate["currency"]
            if currency == "EUR":
                total_cost_eur_cents += amount_cents
                continue
            conv = self._fx.convert(str(amount_cents / 100), currency, "EUR")
            total_cost_eur_cents += round(float(conv["converted_amount"]) * 100)
            fx_rate_used = float(conv["rate"])

        # R2 first -- R1's demo pricing policy needs to know whether FX is
        # over threshold (its +2pp risk adjustment) before it can run.
        prior = self.get_version(quote_id, qv.prior_version) if qv.prior_version else None
        fx_over_threshold = False
        if fx_rate_used is None:
            r2 = RuleResult(
                rule_id="R2", result="not_evaluated",
                reason="every rate_ref was already in EUR -- no FX conversion occurred to compare",
            )
        elif prior is None or prior.fx_rate_snapshot is None:
            r2 = RuleResult(
                rule_id="R2", result="not_evaluated",
                reason="no prior priced version's FX snapshot to compare against (qms-pricing-rules.md: never a live re-fetch)",
            )
        else:
            variance = round(abs(fx_rate_used - prior.fx_rate_snapshot) / prior.fx_rate_snapshot * 1000)
            fx_over_threshold = variance > _R2_THRESHOLD_PCT_X10
            r2 = RuleResult(
                rule_id="R2", actual_pct_x10=variance, threshold_pct_x10=_R2_THRESHOLD_PCT_X10,
                result="over_threshold" if fx_over_threshold else "within_threshold",
            )

        profile = pricing_policy.resolve_profile(qv.margin_floor_ref)
        target_margin = pricing_policy.target_margin_pct_x10(profile, fx_over_threshold=fx_over_threshold)
        unrounded_sell = pricing_policy.calculate_sell_price(total_cost_eur_cents, target_margin)
        sell_price_eur_cents = pricing_policy.commercial_round_up(unrounded_sell)
        actual_margin = pricing_policy.calculate_margin_pct_x10(total_cost_eur_cents, sell_price_eur_cents)
        r1 = RuleResult(
            rule_id="R1", actual_pct_x10=actual_margin, threshold_pct_x10=profile.base_margin_pct_x10,
            result="within_threshold" if actual_margin >= profile.base_margin_pct_x10 else "below_floor",
            reason=(
                f"demo policy {pricing_policy.POLICY_REF}, profile {profile.profile_id!r}: "
                f"target {target_margin / 10}% (base {profile.base_margin_pct_x10 / 10}%"
                f"{' + 2.0% FX risk' if fx_over_threshold else ''}), "
                f"sell price €{sell_price_eur_cents / 100:.2f} rounded up from €{unrounded_sell / 100:.2f}"
            ),
        )

        rule_results = [r1, r2]
        for rule_id in ("R3", "R4", "R5"):
            rule_results.append(RuleResult(rule_id=rule_id, result="not_evaluated", reason=_NOT_EVALUATED_NO_BASELINE))

        updated = qv.model_copy(update={
            "status": "priced",
            "total_cost_eur_cents": total_cost_eur_cents,
            "proposed_sell_price_eur_cents": sell_price_eur_cents,
            "margin_pct_x10": actual_margin,
            "pricing_policy_ref": pricing_policy.POLICY_REF,
            "fx_rate_snapshot": fx_rate_used,
            "pricing_rule_results": rule_results,
        })
        self._replace_version(quote_id, version, updated)
        return updated

    def submit_for_approval(self, quote_id: str, version: int) -> QuoteVersion:
        """priced -> approval_required. R1's `not_evaluated` result means
        margin-floor compliance couldn't be determined -- this doesn't block
        submission (D5/D12 both land on approval_required regardless), but
        the incompleteness must stay visible to the human reviewer (the UI
        surfaces R1's own `reason`, not a silent pass)."""
        qv = self.get_version(quote_id, version)
        if qv is None:
            raise UnknownQuoteError(f"no version {version} for quote {quote_id!r}")
        if qv.status != "priced":
            raise InvalidStateError(f"version {version} of {quote_id!r} is {qv.status!r}, not priced")
        updated = qv.model_copy(update={"status": "approval_required"})
        self._replace_version(quote_id, version, updated)
        return updated

    def record_decision(self, quote_id: str, version: int, body: QuoteDecisionRequest) -> QuoteVersion:
        """The actual D19-candidate action, made real: approval_required ->
        approved|rejected|revise. `status`'s new value IS the decision (per
        QuoteVersion's own docstring) -- DecisionRecord is kept alongside as
        supporting evidence (who/when/why), not the authoritative signal."""
        qv = self.get_version(quote_id, version)
        if qv is None:
            raise UnknownQuoteError(f"no version {version} for quote {quote_id!r}")
        if qv.status != "approval_required":
            raise InvalidStateError(f"version {version} of {quote_id!r} is {qv.status!r}, not approval_required")
        updated = qv.model_copy(update={"status": body.decision})
        self._replace_version(quote_id, version, updated)
        record = DecisionRecord(
            decision=body.decision, approver=body.approver, reason=body.reason, decided_at=_timestamp(),
        )
        self._decisions.setdefault(f"{quote_id}:{version}", []).append(record)
        return updated

    def list_decisions(self, quote_id: str, version: int) -> list[DecisionRecord]:
        return list(self._decisions.get(f"{quote_id}:{version}", []))

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
