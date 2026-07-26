"""M8.4 step 7: policy_model.py's pure pieces against the real committed
authorization/ files (no network -- policy_drift's live half is
exercised in the real-stack checkpoint)."""

from mission_control_api.policy_model import declared_policies, obligation_ids, policies_report, schema_summary


def test_declared_policies_matches_the_real_known_counts():
    policies = declared_policies()
    assert len(policies) == 24
    assert sum(1 for p in policies if p["effect"] == "permit") == 21
    assert sum(1 for p in policies if p["effect"] == "forbid") == 3


def test_schema_summary_matches_the_real_known_counts():
    summary = schema_summary()
    assert summary["entity_type_count"] == 10
    assert summary["action_count"] == 17


def test_obligation_ids_is_a_real_nonempty_list():
    ids = obligation_ids()
    assert ids
    assert "oblig-lane-deviation" in ids


def test_policies_report_shape():
    report = policies_report()
    assert report["permit_count"] == 21
    assert report["forbid_count"] == 3
    assert report["schema"]["entity_type_count"] == 10
