from pathlib import Path

from tools.identity.gen_machine_identity_inventory import build_inventory

ROOT = Path(__file__).resolve().parents[3]


def test_every_mcp_server_has_a_transport_edge_to_its_own_business_system():
    edges = build_inventory()
    pairs = {(e["caller"], e["target"]) for e in edges}
    assert ("tms-mcp", "mock-tms") in pairs
    assert ("rate-mcp", "mock-rate") in pairs
    assert ("qms-mcp", "mock-qms") in pairs
    assert ("approval-mcp", "mock-qms") in pairs


def test_every_mcp_server_has_its_own_keycloak_introspection_edge():
    edges = build_inventory()
    for server in ["tms-mcp", "rate-mcp", "qms-mcp", "approval-mcp"]:
        assert any(
            e["caller"] == server and e["target"].startswith("Keycloak")
            for e in edges
        ), f"missing Keycloak introspection edge for {server}"


def test_no_edge_is_silently_unauthenticated_without_explicit_status():
    """Every edge states a mechanism; 'none' is only ever paired with an
    explicit 'accepted exception' status, never bare."""
    edges = build_inventory()
    for e in edges:
        if e["mechanism"].startswith("none"):
            assert e["status"] == "accepted exception", e


def test_shared_credential_note_is_labelled_credential_level_not_edge_specific():
    edges = build_inventory()
    qms_edges_with_notes = [e for e in edges if e["target"] == "mock-qms" and e.get("note")]
    assert qms_edges_with_notes
    for e in qms_edges_with_notes:
        assert e["note"].startswith("(credential-level note"), e
