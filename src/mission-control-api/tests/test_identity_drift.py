"""M8.5 step 9: identity_drift.py against the real committed identity/
projections and Terraform state files (no network, no Vault, no live
IdP query)."""

from mission_control_api.identity_drift import identity_drift_report


def test_identity_drift_report_has_no_severity_field():
    import json
    report = identity_drift_report()
    assert "severity" not in json.dumps(report)


def test_identity_drift_report_shape():
    report = identity_drift_report()
    assert "keycloak" in report and "entra" in report
    for provider in ("keycloak", "entra"):
        assert "declared_only" in report[provider]
        assert "provisioned_only" in report[provider]
        assert "matched_count" in report[provider]


def test_identity_drift_states_its_own_scope_limits():
    report = identity_drift_report()
    assert "not a live query" in report["basis"]
    assert "human" in report["basis"].lower()
