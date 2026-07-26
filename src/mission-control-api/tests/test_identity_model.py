"""M8.5 step 8: identity_model.py against the real committed identity/
files (no network, no Vault)."""

from mission_control_api.identity_model import identities_report


def test_identities_report_shape_and_known_counts():
    report = identities_report()
    kinds = {p["kind"] for p in report["principals"]}
    assert kinds == {"human", "agent", "workload"}
    assert len(report["groups"]) == 9
    workload_ids = {p["id"] for p in report["principals"] if p["kind"] == "workload"}
    assert "workload.mission-control" in workload_ids


def test_identities_report_never_leaks_a_secret_shaped_value():
    import json
    report = identities_report()
    dumped = json.dumps(report).lower()
    for forbidden in ("secret", "password", "vault_path", "client_secret"):
        assert forbidden not in dumped, f"identities report leaked a {forbidden!r}-shaped field"


def test_agent_capability_profiles_flag_the_test_fixture():
    report = identities_report()
    fixture_profiles = [p for p in report["agent_capability_profiles"] if p["fixture"]]
    assert len(fixture_profiles) == 1
    assert fixture_profiles[0]["id"] == "trust-boundary-fixture-agent"
