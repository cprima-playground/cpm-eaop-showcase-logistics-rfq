"""M8.2 step 5: topology.py's pure pieces -- credential_edges() parses
the real generated inventory file directly (no network); runtime_
dependency_edges() and the full topology() aggregation are exercised
against a live registry in the real-stack checkpoint (test_mission_
control_live.py), not here."""

from pathlib import Path

from mission_control_api.topology import credential_edges

REAL_INVENTORY = Path(__file__).resolve().parents[3] / "data" / "identity" / "machine-identity-inventory.yaml"


def test_credential_edges_parses_the_real_generated_inventory():
    edges = credential_edges(REAL_INVENTORY)
    assert edges, "expected at least one real edge from the generated inventory"
    assert all(e["layer"] == "credential" for e in edges)
    assert ("tms-mcp", "mock-tms") in {(e["from"], e["to"]) for e in edges}


def test_credential_edges_never_carry_a_note_field():
    """The raw inventory's `note` field can be long, credential-adjacent
    free text -- topology's public shape deliberately drops it, keeping
    only from/to/mechanism/status/layer."""
    edges = credential_edges(REAL_INVENTORY)
    assert all("note" not in e for e in edges)
