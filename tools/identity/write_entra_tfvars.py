"""Write infra/entra/entra.generated.tfvars.json from the approved
Validated Identity Model. Mirrors write_keycloak_tfvars.py's RETAIN
exclusion so both IdPs provision the identical generator-owned set --
required for M3.4's parity check (aiden.ashford stays excluded from
BOTH, not just Keycloak, until he's properly modeled with a real
identity/groups.yaml group).
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.identity.gen_entra import generate_entra_input
from tools.identity.validator import validate_identity
from tools.identity.write_keycloak_tfvars import RETAIN_USERNAMES

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    model = validate_identity(
        ROOT / "identity" / "actors.yaml",
        ROOT / "identity" / "groups.yaml",
        ROOT / "business" / "departments.yaml",
        ROOT / "business" / "job-titles.yaml",
    )
    data = generate_entra_input(model, ROOT / "identity" / "projections" / "entra.yaml")
    data["users"] = [u for u in data["users"] if u["upn"].split("@")[0] not in RETAIN_USERNAMES]
    data["group_memberships"] = [
        m for m in data["group_memberships"] if m["upn"].split("@")[0] not in RETAIN_USERNAMES
    ]

    out_path = ROOT / "infra" / "entra" / "entra.generated.tfvars.json"
    out_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path}: {len(data['users'])} users, {len(data['groups'])} groups, "
          f"{len(data['app_registrations'])} app registrations")


if __name__ == "__main__":
    main()
