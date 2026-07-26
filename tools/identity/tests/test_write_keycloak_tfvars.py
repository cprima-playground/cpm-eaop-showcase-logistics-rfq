import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _run_stage(stage: str, tmp_path: Path) -> dict:
    out_path = tmp_path / "keycloak.generated.tfvars.json"
    subprocess.run(
        [sys.executable, "-m", "tools.identity.write_keycloak_tfvars", "--stage", stage, "--out", str(out_path)],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    return json.loads(out_path.read_text())


def test_stage_b_excludes_retained_aiden(tmp_path):
    """Live 409 Conflict discovered during M3.2b apply: aiden.ashford is
    RETAIN-classified (MIGRATION.md) but was previously generated anyway,
    colliding with his hand-authored resource. Must never regress."""
    data = _run_stage("b", tmp_path)
    usernames = {u["username"] for u in data["users"]}
    assert "aiden.ashford" not in usernames
    memberships_usernames = {m["username"] for m in data["group_memberships"]}
    assert "aiden.ashford" not in memberships_usernames


def test_stage_a_still_scoped_to_three(tmp_path):
    data = _run_stage("a", tmp_path)
    assert {u["username"] for u in data["users"]} == {"diane.delgado", "mona.commercial", "sam.pricing"}
