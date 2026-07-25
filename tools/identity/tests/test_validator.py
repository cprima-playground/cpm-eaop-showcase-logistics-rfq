from pathlib import Path

import pytest
import yaml

from tools.identity.validator import IdentityValidationError, validate_identity

ROOT = Path(__file__).resolve().parents[3]


def test_real_identity_files_validate_cleanly():
    model = validate_identity(
        ROOT / "identity" / "actors.yaml",
        ROOT / "identity" / "groups.yaml",
        ROOT / "business" / "departments.yaml",
        ROOT / "business" / "job-titles.yaml",
    )
    kinds = {p.kind for p in model.principals}
    assert kinds == {"human", "agent", "workload"}
    workloads = [p for p in model.principals if p.kind == "workload"]
    assert {w.id for w in workloads} == {
        "workload.tms-mcp", "workload.rate-mcp", "workload.qms-mcp", "workload.approval-mcp",
    }


def test_job_title_and_department_ids_resolve():
    model = validate_identity(
        ROOT / "identity" / "actors.yaml",
        ROOT / "identity" / "groups.yaml",
        ROOT / "business" / "departments.yaml",
        ROOT / "business" / "job-titles.yaml",
    )
    procurement = next(p for p in model.principals if p.id == "human.felix.procurement")
    assert procurement.job_title_id == "carrier-procurement-specialist"
    assert procurement.department_id == "carrier-procurement"

    admin = next(p for p in model.principals if p.id == "aiden.ashford")
    assert admin.department_id is None


def test_keycloak_client_is_never_carried_forward():
    """Decision #11: keycloak_client is provider-specific projection config,
    not an identity fact. CanonicalPrincipal has no such field at all -- even
    if a raw actor dict still had one (e.g. a future regression re-adding it),
    it would be silently dropped by validation (extra='ignore'), never
    reaching the Validated Identity Model."""
    model = validate_identity(ROOT / "identity" / "actors.yaml", ROOT / "identity" / "groups.yaml")
    assert not any(hasattr(p, "keycloak_client") for p in model.principals)

    raw_with_extra = {"id": "a.test", "kind": "human", "keycloak_client": "should-be-dropped"}
    from tools.identity.validator import CanonicalPrincipal
    principal = CanonicalPrincipal.model_validate(raw_with_extra)
    assert not hasattr(principal, "keycloak_client")


def _write(tmp_path, actors, groups):
    actors_path = tmp_path / "actors.yaml"
    groups_path = tmp_path / "groups.yaml"
    actors_path.write_text(yaml.safe_dump({"actors": actors}), encoding="utf-8")
    groups_path.write_text(yaml.safe_dump({"groups": groups}), encoding="utf-8")
    return actors_path, groups_path


def test_orphaned_member_of_rejected(tmp_path):
    actors_path, groups_path = _write(
        tmp_path,
        actors=[{"id": "a.1", "kind": "human", "member_of": ["ghost-group"]}],
        groups=[],
    )
    with pytest.raises(IdentityValidationError) as exc:
        validate_identity(actors_path, groups_path)
    assert any("orphaned member_of" in p for p in exc.value.problems)


def test_duplicate_id_rejected(tmp_path):
    actors_path, groups_path = _write(
        tmp_path,
        actors=[{"id": "a.1", "kind": "human"}, {"id": "a.1", "kind": "agent"}],
        groups=[],
    )
    with pytest.raises(IdentityValidationError) as exc:
        validate_identity(actors_path, groups_path)
    assert any("duplicate canonical id" in p for p in exc.value.problems)


def test_unknown_kind_rejected(tmp_path):
    actors_path, groups_path = _write(
        tmp_path,
        actors=[{"id": "a.1", "kind": "robot"}],
        groups=[],
    )
    with pytest.raises(IdentityValidationError) as exc:
        validate_identity(actors_path, groups_path)
    assert any("a.1" in p for p in exc.value.problems)


def test_unknown_manager_rejected(tmp_path):
    actors_path, groups_path = _write(
        tmp_path,
        actors=[{"id": "a.1", "kind": "human", "manager": "nobody"}],
        groups=[],
    )
    with pytest.raises(IdentityValidationError) as exc:
        validate_identity(actors_path, groups_path)
    assert any("not a known actor id" in p for p in exc.value.problems)


def test_unknown_job_title_id_rejected(tmp_path):
    actors_path, groups_path = _write(
        tmp_path,
        actors=[{"id": "a.1", "kind": "human", "job_title_id": "made-up-title"}],
        groups=[],
    )
    departments_path = tmp_path / "departments.yaml"
    job_titles_path = tmp_path / "job-titles.yaml"
    departments_path.write_text(yaml.safe_dump({"departments": []}), encoding="utf-8")
    job_titles_path.write_text(yaml.safe_dump({"job_titles": [{"job_title_id": "real-title"}]}), encoding="utf-8")
    with pytest.raises(IdentityValidationError) as exc:
        validate_identity(actors_path, groups_path, departments_path, job_titles_path)
    assert any("unknown job_title_id" in p for p in exc.value.problems)


def test_management_layer_skip_rejected(tmp_path):
    """A specialist reporting straight to a director, skipping a manager
    layer the job-title schema declares, is a validation error."""
    actors_path, groups_path = _write(
        tmp_path,
        actors=[
            {"id": "dir", "kind": "human", "job_title_id": "director"},
            {"id": "spec", "kind": "human", "job_title_id": "specialist", "manager": "dir"},
        ],
        groups=[],
    )
    departments_path = tmp_path / "departments.yaml"
    job_titles_path = tmp_path / "job-titles.yaml"
    departments_path.write_text(yaml.safe_dump({"departments": []}), encoding="utf-8")
    job_titles_path.write_text(yaml.safe_dump({"job_titles": [
        {"job_title_id": "director"},
        {"job_title_id": "manager", "reports_to_job_title_id": "director"},
        {"job_title_id": "specialist", "reports_to_job_title_id": "manager"},
    ]}), encoding="utf-8")
    with pytest.raises(IdentityValidationError) as exc:
        validate_identity(actors_path, groups_path, departments_path, job_titles_path)
    assert any("skips the management layer" in p for p in exc.value.problems)


def test_correct_management_chain_passes(tmp_path):
    actors_path, groups_path = _write(
        tmp_path,
        actors=[
            {"id": "dir", "kind": "human", "job_title_id": "director"},
            {"id": "mgr", "kind": "human", "job_title_id": "manager", "manager": "dir"},
            {"id": "spec", "kind": "human", "job_title_id": "specialist", "manager": "mgr"},
        ],
        groups=[],
    )
    departments_path = tmp_path / "departments.yaml"
    job_titles_path = tmp_path / "job-titles.yaml"
    departments_path.write_text(yaml.safe_dump({"departments": []}), encoding="utf-8")
    job_titles_path.write_text(yaml.safe_dump({"job_titles": [
        {"job_title_id": "director"},
        {"job_title_id": "manager", "reports_to_job_title_id": "director"},
        {"job_title_id": "specialist", "reports_to_job_title_id": "manager"},
    ]}), encoding="utf-8")
    model = validate_identity(actors_path, groups_path, departments_path, job_titles_path)
    assert len(model.principals) == 3


def test_valid_minimal_directory_passes(tmp_path):
    actors_path, groups_path = _write(
        tmp_path,
        actors=[
            {"id": "boss", "kind": "human"},
            {"id": "a.1", "kind": "human", "manager": "boss", "member_of": ["g1"]},
            {"id": "workload.x", "kind": "workload", "system": "x", "trust_domain": "internal"},
        ],
        groups=[{"group_id": "g1", "path": "/G1", "cost_center": "CC1"}],
    )
    model = validate_identity(actors_path, groups_path)
    assert len(model.principals) == 3
    assert len(model.groups) == 1
