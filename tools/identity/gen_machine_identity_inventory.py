"""Machine-identity/trust-boundary inventory generator (M6, decision #8).

Mechanically derives every service-to-service auth EDGE this repo actually
has, from the data that already describes it -- never a hand-maintained,
driftable list:

  identity/credentials-inventory.yaml  -- consumers: on each *-api-key
      credential = transport-auth edges (MCP/agent -> business system,
      "shared API key" mechanism); consumers: on each *-svc-client-secret
      credential = a workload's own OIDC confidential-client identity,
      used for RFC 7662 introspection of inbound caller tokens.

Two edge kinds intentionally NOT derivable from any YAML today are declared
as an explicit, small, hand-authored constant below (_STATIC_EDGES) rather
than silently omitted -- decision #8 requires every edge enumerated, and an
edge with no credential at all (e.g. cedar-agent, reachable only over the
internal compose network, no auth) is still an edge that needs stating,
not a gap this generator can pretend doesn't exist.

Output: data/identity/machine-identity-inventory.yaml (structured, this
module's real output) + docs/adr/machine-identity-inventory.md (rendered
table, GENERATED -- do not hand-edit, re-run this module instead).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CREDENTIALS_INVENTORY = REPO_ROOT / "identity" / "credentials-inventory.yaml"
DATA_OUT = REPO_ROOT / "data" / "identity" / "machine-identity-inventory.yaml"
DOC_OUT = REPO_ROOT / "docs" / "adr" / "machine-identity-inventory.md"

# credential-name prefix -> the business system it authenticates callers TO.
# Fixed, small, real (one entry per mock-* system this repo actually has) --
# not inferred from natural-language `purpose` text, which isn't reliably
# parseable.
_API_KEY_TARGET_SYSTEM = {
    "fx-api-key": "mock-fx",
    "masterdata-api-key": "mock-masterdata",
    "tms-api-key": "mock-tms",
    "rate-api-key": "mock-rate",
    "qms-api-key": "mock-qms",
}

# Edges with no derivable credential in identity/credentials-inventory.yaml
# today -- stated explicitly per decision #8, not silently gapped.
_STATIC_EDGES: list[dict[str, Any]] = [
    {
        "caller": "rfq_common.pdp.PDPClient (every service that authorizes)",
        "target": "cedar-agent",
        "mechanism": "none -- network-only trust",
        "status": "accepted exception",
        "note": (
            "cedar-agent is never published on a host port and only "
            "reachable over the internal compose network "
            "(infra/compose.support.yaml has no cedar-agent service today; "
            "the real cedar-agent runs standalone, container_name "
            "rfq-showcase-cedar-agent, compose-internal-only). No request "
            "credential is checked on POST /v1/is_authorized. Accepted for "
            "this showcase's scope because the only callers are this "
            "repo's own trusted services on a private network, never an "
            "external caller -- same class of deliberate scope call as the "
            "shared-API-key transport edges below, not an oversight."
        ),
    },
    {
        "caller": "infra/keycloak/terraform (Terraform apply, human-triggered)",
        "target": "Keycloak admin API",
        "mechanism": "keycloak-realm-admin-password (identity/credentials-inventory.yaml)",
        "status": "real",
        "note": "Provisions realm/clients/workload identities -- not a runtime service edge, an operator edge.",
    },
]


class MachineIdentityInventoryError(Exception):
    pass


def _load_credentials(path: Path) -> list[dict[str, Any]]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return doc.get("credentials", [])


def _transport_edges(credentials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """MCP/agent -> business system, authenticated with a shared API key
    (decision #8's accepted weaker-than-per-workload-token granularity)."""
    edges: list[dict[str, Any]] = []
    for cred in credentials:
        name = cred["name"]
        target = _API_KEY_TARGET_SYSTEM.get(name)
        if target is None:
            continue
        consumers = [c for c in cred.get("consumers", []) if c != target]
        note = (cred.get("note") or "").strip() or None
        # cred['note'] describes the CREDENTIAL, not any one consumer -- it
        # may read as being about a specific service (whichever one the
        # note's author had in mind) even though it's attached identically
        # to every consumer's edge below. Label it as such rather than
        # letting it read as edge-specific when it isn't.
        if note:
            note = f"(credential-level note, shared by every consumer of {name}) {note}"
        for caller in consumers:
            edges.append({
                "caller": caller,
                "target": target,
                "mechanism": f"shared API key ({name})",
                "status": "real",
                "note": note,
            })
    return edges


def _workload_identity_edges(credentials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A workload's own OIDC confidential-client secret, used for RFC 7662
    introspection of an inbound caller's bearer token -- the resource
    server authenticating ITSELF to Keycloak, distinct from transport auth
    to its downstream business system."""
    edges: list[dict[str, Any]] = []
    for cred in credentials:
        name = cred["name"]
        if not name.endswith("-svc-client-secret"):
            continue
        for caller in cred.get("consumers", []):
            edges.append({
                "caller": caller,
                "target": "Keycloak (token introspection, RFC 7662)",
                "mechanism": f"OIDC confidential client, workload's own identity ({name})",
                "status": "real",
                "note": (cred.get("note") or "").strip() or None,
            })
    return edges


def build_inventory(credentials_inventory_path: Path = CREDENTIALS_INVENTORY) -> list[dict[str, Any]]:
    credentials = _load_credentials(credentials_inventory_path)
    edges = _transport_edges(credentials) + _workload_identity_edges(credentials) + list(_STATIC_EDGES)
    edges.sort(key=lambda e: (e["caller"], e["target"]))
    return edges


def _render_markdown(edges: list[dict[str, Any]]) -> str:
    lines = [
        "# Machine-identity / trust-boundary inventory",
        "",
        "GENERATED -- do not hand-edit. Source: `identity/credentials-inventory.yaml`"
        " + a small static list of edges that carry no credential at all"
        " (see `tools/identity/gen_machine_identity_inventory.py`'s"
        " `_STATIC_EDGES`). Re-run `uv run python -m"
        " tools.identity.gen_machine_identity_inventory` after any change"
        " to `identity/credentials-inventory.yaml`.",
        "",
        "Every service-to-service auth edge this repo actually has (decision"
        " #8, M6). Any edge with a weaker-than-workload-token mechanism"
        " (`shared API key`, `none`) is a DELIBERATE, ALREADY-ACCEPTED scope"
        " call, documented at the credential's own `note` in"
        " `identity/credentials-inventory.yaml` -- not a silent gap.",
        "",
        "| Caller | Target | Mechanism | Status |",
        "| --- | --- | --- | --- |",
    ]
    for e in edges:
        lines.append(f"| {e['caller']} | {e['target']} | {e['mechanism']} | {e['status']} |")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    for e in edges:
        if e.get("note"):
            lines.append(f"- **{e['caller']} -> {e['target']}**: {e['note']}")
    lines.append("")
    return "\n".join(lines)


def write_outputs(edges: list[dict[str, Any]] | None = None) -> None:
    edges = edges if edges is not None else build_inventory()
    DATA_OUT.parent.mkdir(parents=True, exist_ok=True)
    DATA_OUT.write_text(
        "# GENERATED -- do not hand-edit. Run tools/identity/gen_machine_identity_inventory.py.\n"
        + yaml.safe_dump({"edges": edges}, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    DOC_OUT.parent.mkdir(parents=True, exist_ok=True)
    DOC_OUT.write_text(_render_markdown(edges), encoding="utf-8")


if __name__ == "__main__":
    write_outputs()
    print(f"wrote {DATA_OUT}")
    print(f"wrote {DOC_OUT}")
