"""Identity Validator (implementation plan M3.1).

Turns identity/actors.yaml + identity/groups.yaml's raw, IdP-neutral facts
into a Validated Identity Model: canonical principals only, still provider-
and Cedar-instance-neutral. Nothing downstream (Keycloak/Entra Terraform
input, Cedar entity data) is generated here -- that's M3.5, gated behind the
STOP AND REVIEW checkpoint this validator's output feeds into.

Provider-specific fields (e.g. `keycloak_client`) are dropped, not carried
forward -- CanonicalPrincipal has no such field, so constructing one from a
raw actor dict silently normalizes it away (implementation plan decision
#11's flagged cleanup for the 3 pre-existing agent entries).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

Kind = Literal["human", "agent", "workload"]


class ApprovalLimit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    currency: str
    amount_cents: int


class CanonicalPrincipal(BaseModel):
    """Provider- and Cedar-instance-neutral. Unknown fields (provider-
    specific config like `keycloak_client`) are silently dropped, not an
    error -- that's the normalization this validator performs."""

    model_config = ConfigDict(extra="ignore")

    id: str
    kind: Kind
    name: str | None = None
    persona: str | None = None
    job_title_id: str | None = None    # -> business/job-titles.yaml
    department_id: str | None = None   # -> business/departments.yaml
    region: str | None = None
    manager: str | None = None
    member_of: list[str] = []
    approval_limit: ApprovalLimit | None = None
    system: str | None = None
    trust_domain: str | None = None


class CanonicalGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    group_id: str
    path: str
    cost_center: str


class ValidatedIdentityModel(BaseModel):
    principals: list[CanonicalPrincipal]
    groups: list[CanonicalGroup]


class IdentityValidationError(Exception):
    """Raised with every problem found, not just the first."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("\n".join(problems))


def _load_yaml(path: Path, key: str) -> list[dict]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return doc.get(key, [])


def validate_identity(
    actors_path: Path,
    groups_path: Path,
    departments_path: Path | None = None,
    job_titles_path: Path | None = None,
) -> ValidatedIdentityModel:
    problems: list[str] = []

    raw_groups = _load_yaml(groups_path, "groups")
    groups: list[CanonicalGroup] = []
    for raw in raw_groups:
        try:
            groups.append(CanonicalGroup.model_validate(raw))
        except ValidationError as exc:
            problems.append(f"group {raw.get('group_id', '<unknown>')!r}: {exc}")

    group_ids = {g.group_id for g in groups}
    dup_group_ids = {gid for gid in group_ids if [g.group_id for g in groups].count(gid) > 1}
    for gid in dup_group_ids:
        problems.append(f"duplicate group_id: {gid!r}")

    raw_actors = _load_yaml(actors_path, "actors")
    principals: list[CanonicalPrincipal] = []
    for raw in raw_actors:
        try:
            principals.append(CanonicalPrincipal.model_validate(raw))
        except ValidationError as exc:
            problems.append(f"actor {raw.get('id', '<unknown>')!r}: {exc}")

    seen_ids: set[str] = set()
    for p in principals:
        if p.id in seen_ids:
            problems.append(f"duplicate canonical id: {p.id!r}")
        seen_ids.add(p.id)

    principal_ids = {p.id for p in principals}
    for p in principals:
        for g in p.member_of:
            if g not in group_ids:
                problems.append(f"actor {p.id!r}: orphaned member_of group {g!r}")
        if p.manager is not None and p.manager not in principal_ids:
            problems.append(f"actor {p.id!r}: manager {p.manager!r} is not a known actor id")

    if departments_path is not None:
        dept_ids = {d["department_id"] for d in _load_yaml(departments_path, "departments")}
        for p in principals:
            if p.department_id is not None and p.department_id not in dept_ids:
                problems.append(f"actor {p.id!r}: unknown department_id {p.department_id!r}")

    if job_titles_path is not None:
        raw_titles = _load_yaml(job_titles_path, "job_titles")
        title_ids = {t["job_title_id"] for t in raw_titles}
        reports_to_by_title = {t["job_title_id"]: t.get("reports_to_job_title_id") for t in raw_titles}
        for p in principals:
            if p.job_title_id is not None and p.job_title_id not in title_ids:
                problems.append(f"actor {p.id!r}: unknown job_title_id {p.job_title_id!r}")

        # Management-chain check: if this title declares an expected manager
        # title, the actor's manager must actually hold that title -- catches
        # a specialist skipping a management layer that exists (e.g.
        # reporting straight to the Director instead of the Pricing Manager).
        principals_by_id = {p.id: p for p in principals}
        for p in principals:
            expected_title = p.job_title_id and reports_to_by_title.get(p.job_title_id)
            if expected_title is None or p.manager is None:
                continue
            manager = principals_by_id.get(p.manager)
            if manager is not None and manager.job_title_id != expected_title:
                problems.append(
                    f"actor {p.id!r}: job_title_id {p.job_title_id!r} expects a manager with "
                    f"job_title_id {expected_title!r}, but manager {p.manager!r} has "
                    f"job_title_id {manager.job_title_id!r} (skips the management layer)"
                )

    if problems:
        raise IdentityValidationError(problems)

    return ValidatedIdentityModel(principals=principals, groups=groups)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    model = validate_identity(
        root / "identity" / "actors.yaml",
        root / "identity" / "groups.yaml",
        root / "business" / "departments.yaml",
        root / "business" / "job-titles.yaml",
    )
    by_kind: dict[str, int] = {}
    for p in model.principals:
        by_kind[p.kind] = by_kind.get(p.kind, 0) + 1
    print(f"Validated {len(model.principals)} principals, {len(model.groups)} groups.")
    print("By kind:", by_kind)


if __name__ == "__main__":
    main()
