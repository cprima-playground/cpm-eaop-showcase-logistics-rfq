"""Cedar entity uid ref helpers. Namespace-parameterized (default "Agentic" --
this showcase's namespace) so any future mock-system package can reuse this for
its own Cedar entities without hardcoding the namespace."""

from __future__ import annotations

DEFAULT_NS = "Agentic"


def ref(etype: str, eid: str, *, ns: str = DEFAULT_NS) -> str:
    return f'{ns}::{etype}::"{eid}"'


def action_ref(action: str, *, ns: str = DEFAULT_NS) -> str:
    return f'{ns}::Action::"{action}"'


def uid(etype: str, eid: str, *, ns: str = DEFAULT_NS) -> dict:
    return {"type": f"{ns}::{etype}", "id": eid}


def entity(etype: str, eid: str, attrs: dict, *, parents: list[dict] | None = None, ns: str = DEFAULT_NS) -> dict:
    """A full Cedar entity record ({uid, attrs, parents}) -- same shape
    DataAdmin.put() expects for the persisted store, but built for
    request-time use as PDPClient.authorize()'s `additional_entities`
    (M6, qms-mcp's resource/state-sensitive authorization): supplies a
    freshly-fetched business-system fact (e.g. a Quote's real current
    `status`) for exactly ONE decision, without writing it into
    cedar-agent's persisted entity store. Request-handling code must
    never call DataAdmin directly (admin ops are deliberately
    unreachable from there, per rfq_common.pdp.admin's module docstring)
    -- this is the sanctioned alternative for resource facts that change
    per request."""
    return {"uid": uid(etype, eid, ns=ns), "attrs": attrs, "parents": parents or []}
