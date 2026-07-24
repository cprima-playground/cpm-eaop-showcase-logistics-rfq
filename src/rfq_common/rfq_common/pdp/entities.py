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
