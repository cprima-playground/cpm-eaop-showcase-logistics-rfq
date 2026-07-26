"""authorize()/authorize_and_enforce() -- ADR-004's control-flow contract,
implemented. Layer: rfq_common.pdp -> rfq_common.pep (this module) -> MCP
servers. Imports rfq_common.pdp (the PDP client + PolicyBundle, lower
layer) but NOT any individual business system's code -- this library must
stay reusable across every MCP server, not coupled to one.

AuthorizedContext is deliberately small (per review): canonical principal,
the Cedar refs the decision was made against, obligations, and decision
metadata for auditing. No business payloads, no ORM objects, no request
bodies -- if a caller needs those, it already has them from its own
request handling; this library doesn't carry them.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from opentelemetry import metrics, trace

from rfq_common.pdp import AuthorizationDecision, PDPClient, PolicyBundle
from rfq_common.pdp.entities import ref

from .resolve import ResolvedPrincipal

DEFAULT_ROOT = Path(__file__).resolve().parents[4]

_PRINCIPAL_ENTITY_TYPE = {"human": "Principal", "agent": "AgentPrincipal", "workload": "Workload"}

# M5.9: real, standardized instrumentation on the ACTUAL Cedar decision
# call site (not synthesized elsewhere). get_tracer/get_meter are safe to
# call at import time -- both return no-op implementations until
# rfq_common.observability.configure_observability() sets the real
# providers, per the OTel SDK's own design; no ordering dependency on
# when configure_observability() runs relative to this module's import.
_tracer = trace.get_tracer("rfq_common.pep")
_meter = metrics.get_meter("rfq_common.pep")
_authz_duration = _meter.create_histogram(
    "cedar.authorization.duration", unit="s", description="Cedar is_authorized call latency",
)
_authz_permit = _meter.create_counter("cedar.authorization.permit", description="Cedar permit decisions")
_authz_deny = _meter.create_counter("cedar.authorization.deny", description="Cedar deny decisions")
# Label set is `action` ONLY -- never principal/resource ids (M5.9's hard
# cardinality rule: canonical principal ids, correlation ids, task ids,
# quote ids must never become metric labels).


class AuthorizationDenied(Exception):
    def __init__(self, decision: AuthorizationDecision, principal: ResolvedPrincipal, action: str, resource: str):
        self.decision = decision
        self.principal = principal
        self.action = action
        self.resource = resource
        super().__init__(
            f"denied: {principal.kind}:{principal.id!r} -> {action!r} on {resource!r} "
            f"(determining_policies={decision.determining_policies})"
        )


class ObligationEnforcementError(Exception):
    def __init__(self, obligation_id: str, reason: str):
        self.obligation_id = obligation_id
        self.reason = reason
        super().__init__(f"obligation {obligation_id!r} could not be enforced: {reason}")


@dataclass
class AuthorizedContext:
    """Auditable answer to: who acted, on what, which action, permit/deny,
    which obligations, which provider authenticated them, what canonical
    principal was resolved. Deliberately does not carry business state.

    `principal` is always the EXECUTING identity (whoever Cedar's request
    named as principal -- an agent, in every MCP-mediated call per ADR-001
    decision #3).

    `delegated_by`, when set, is a CLAIMED delegator, not a verified one --
    review round 2's finding, load-bearing enough to restate here, not just
    in ADR-004: this library copies `context["delegated_by"]` verbatim into
    the audit trail with NO resolution, signature check, delegation-record
    lookup, or Cedar entity reference establishing that the named human
    actually authorized this call. Today, any caller that can construct the
    `context` dict can put any string here. `authorize_and_enforce` does
    not verify it and never has -- verifying delegation provenance is
    ADR-003's job (explicitly deferred, not yet designed). Until an ADR-003
    delegation-establishment path exists (verified human token + agent
    handoff / signed delegation artifact / server-side delegation record /
    trusted gateway-injected claim), `delegated_by` MUST only be populated
    by a caller that itself trusts the value -- never pass through
    arbitrary MCP/tool request input unchanged. See
    test_delegated_by_claim_carries_no_authorization_weight for what this
    means concretely: Cedar's decision is IDENTICAL whether this names a
    real accountable human or a fabricated one -- the field carries zero
    authorization weight today, audit metadata only."""
    principal: ResolvedPrincipal
    action: str
    resource: str
    decision: AuthorizationDecision
    obligations: list[str] = field(default_factory=list)
    delegated_by: str | None = None
    executing_workload: str | None = None

    def audit_record(self) -> dict:
        """Flat dict, log-line-ready -- the auditability guarantee made
        concrete: every field an audit record needs, without the caller
        reconstructing them from the principal/decision objects itself.
        Records BOTH the claimed delegator (delegated_by, if any) and the
        executing identity (principal + executing_workload) distinctly --
        checkpoint property #5. Key is `claimed_delegator`, not
        `accountable_principal` -- the latter would overstate what's
        actually established (see class docstring)."""
        return {
            "principal_kind": self.principal.kind,
            "principal_id": self.principal.id,
            "principal_provider": self.principal.provider,
            "claimed_delegator": self.delegated_by,
            "executing_workload": self.executing_workload,
            "action": self.action,
            "resource": self.resource,
            "effect": self.decision.effect,
            "determining_policies": self.decision.determining_policies,
            "obligations": self.obligations,
        }


def principal_ref(principal: ResolvedPrincipal) -> str:
    return ref(_PRINCIPAL_ENTITY_TYPE[principal.kind], principal.id)


def authorize(cedar_url: str, principal: ResolvedPrincipal, action: str, resource: str,
              context: dict | None = None, *,
              additional_entities: list[dict] | None = None) -> AuthorizationDecision:
    """Thin wrapper over PDPClient.authorize() -- never raises for a deny,
    the decision is the caller's to interpret. Use authorize_and_enforce()
    when the decision should gate execution.

    `additional_entities`: request-scoped resource facts (see PDPClient.
    authorize's docstring and rfq_common.pdp.entities.entity()) -- for
    when a policy needs a LIVE business-system fact (e.g. a Quote's
    current status) that isn't, and must never become, part of the
    persisted Cedar entity store."""
    client = PDPClient(cedar_url)
    with _tracer.start_as_current_span("cedar.authorize") as span:
        span.set_attribute("cedar.action", action)
        span.set_attribute("cedar.principal.kind", principal.kind)
        t0 = time.monotonic()
        decision = client.authorize(
            principal=principal_ref(principal),
            action=f'Agentic::Action::"{action}"',
            resource=resource,
            context=context or {},
            additional_entities=additional_entities,
        )
        duration = time.monotonic() - t0

        span.set_attribute("cedar.decision.effect", decision.effect)
        span.set_attribute("cedar.decision.determining_policies", ",".join(decision.determining_policies))
        _authz_duration.record(duration, {"action": action})
        (_authz_permit if decision.effect == "allow" else _authz_deny).add(1, {"action": action})

    return decision


def _load_known_obligation_ids(root: Path) -> set[str]:
    doc = yaml.safe_load((root / "authorization" / "obligations.yaml").read_text(encoding="utf-8"))
    return set(doc.get("obligations", {}).keys())


def authorize_and_enforce(
    cedar_url: str,
    bundle: PolicyBundle,
    principal: ResolvedPrincipal,
    action: str,
    resource: str,
    context: dict | None = None,
    *,
    root: Path | None = None,
    additional_entities: list[dict] | None = None,
) -> AuthorizedContext:
    """Raises AuthorizationDenied on deny. Raises ObligationEnforcementError
    when Cedar permits but a returned obligation id has no entry in
    authorization/obligations.yaml -- Cedar said permit, but enforcing what
    that permit requires failed; a different failure category from denial,
    see ADR-004.

    `additional_entities`: see authorize()'s docstring -- request-scoped
    resource facts, never persisted."""
    root = root or DEFAULT_ROOT
    decision = authorize(cedar_url, principal, action, resource, context, additional_entities=additional_entities)

    if decision.effect != "allow":
        raise AuthorizationDenied(decision, principal, action, resource)

    obligation_ids = bundle.resolve_obligation_ids(decision.determining_policies)
    known = _load_known_obligation_ids(root)
    for oid in obligation_ids:
        if oid not in known:
            raise ObligationEnforcementError(oid, f"not defined in authorization/obligations.yaml (known: {sorted(known)})")

    context = context or {}
    return AuthorizedContext(
        principal=principal, action=action, resource=resource,
        decision=decision, obligations=obligation_ids,
        delegated_by=context.get("delegated_by"),
        executing_workload=context.get("executing_workload"),
    )
