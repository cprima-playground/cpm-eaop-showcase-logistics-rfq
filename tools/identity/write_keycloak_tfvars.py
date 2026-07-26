"""Write infra/keycloak/terraform/keycloak.generated.tfvars.json from the
approved Validated Identity Model, filtered to the M3.2a/M3.2b split
(MIGRATION.md's classification table).

Usage: uv run --with pydantic --with pyyaml python -m tools.identity.write_keycloak_tfvars --stage a|b
  stage a: only the 3 humans + 2 groups already live (zero-diff refactor)
  stage b: full set (adds the rest -- new humans/groups/machine clients)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.identity.gen_keycloak import generate_keycloak_input
from tools.identity.validator import validate_identity

ROOT = Path(__file__).resolve().parents[2]
STAGE_A_USERNAMES = {"diane.delgado", "mona.commercial", "sam.pricing"}
STAGE_A_GROUP_IDS = {"rfq-commercial-emea", "rfq-pricing-emea"}

# MIGRATION.md classification: RETAIN, hand-authored, never generator-owned.
# aiden.ashford's live group (rfq_qms_platform) isn't in identity/
# groups.yaml's 9-group model -- generating him would either drop that
# membership or (as discovered live) collide with his existing hand-authored
# resource (409 Conflict: duplicate email).
RETAIN_USERNAMES = {"aiden.ashford"}


def _filter_stage_a(data: dict) -> dict:
    return {
        "realm": data["realm"],
        "users": [u for u in data["users"] if u["username"] in STAGE_A_USERNAMES],
        "groups": [g for g in data["groups"] if g["group_id"] in STAGE_A_GROUP_IDS],
        "group_memberships": [
            m for m in data["group_memberships"]
            if m["username"] in STAGE_A_USERNAMES and m["group_id"] in STAGE_A_GROUP_IDS
        ],
        "clients": [],  # M3.2b only
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["a", "b"], required=True)
    parser.add_argument("--out", type=Path, default=None,
                         help="Override output path (tests use this to avoid mutating the real generated file)")
    args = parser.parse_args()

    model = validate_identity(
        ROOT / "identity" / "actors.yaml",
        ROOT / "identity" / "groups.yaml",
        ROOT / "business" / "departments.yaml",
        ROOT / "business" / "job-titles.yaml",
    )
    data = generate_keycloak_input(model, ROOT / "identity" / "projections" / "keycloak.yaml")
    data["users"] = [u for u in data["users"] if u["username"] not in RETAIN_USERNAMES]
    data["group_memberships"] = [m for m in data["group_memberships"] if m["username"] not in RETAIN_USERNAMES]

    if args.stage == "a":
        data = _filter_stage_a(data)

    out_path = args.out or (ROOT / "infra" / "keycloak" / "terraform" / "keycloak.generated.tfvars.json")
    out_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path} (stage {args.stage}): "
          f"{len(data['users'])} users, {len(data['groups'])} groups, {len(data['clients'])} clients")


if __name__ == "__main__":
    main()
