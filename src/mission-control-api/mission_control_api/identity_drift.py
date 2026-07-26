"""M8.5 step 9: GET /api/v1/identity-drift. Declared-vs-Terraform-state
comparison ONLY (D3) -- credential-free, both sides are files on disk,
no live IdP query, no Vault read. Explicitly NOT credential health
(does the stored secret still authenticate?) -- that's
rfq_common.pep.preflight.preflight_machine_identity, a live-grant check
requiring Vault access this service deliberately never has.

Transitional posture, stated explicitly (review feedback, D3): reading
raw .tfstate files is credential-free but not a good long-term
architecture -- state files can carry sensitive material even when this
diff never touches it, and coupling to Terraform's own state format is
fragile. A future milestone should replace this with a sanitized,
generated provisioning projection instead of reading state directly.

Scope: MACHINE identities only (agents + workloads) -- the
security-relevant set decision #8's own inventory already focuses on.
Human provisioning drift is not covered here; stated in `basis`, not
silently implied as covered.

No `severity` field anywhere in this module's output -- severity is a
policy judgement (CLAUDE.md), not built here."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

RFQ_ROOT = Path(__file__).resolve().parents[3]
KEYCLOAK_STATE_PATH = RFQ_ROOT / "infra" / "keycloak" / "terraform" / "terraform.tfstate"
ENTRA_STATE_PATH = RFQ_ROOT / "infra" / "entra" / "terraform.tfstate"
KEYCLOAK_PROJECTION_PATH = RFQ_ROOT / "identity" / "projections" / "keycloak.yaml"
ENTRA_PROJECTION_PATH = RFQ_ROOT / "identity" / "projections" / "entra.yaml"

BASIS = (
    "declared projection vs. Terraform state on disk -- not a live query "
    "against either IdP, not a credential-health check (does the stored "
    "secret still authenticate? -- see rfq_common.pep.preflight for that, "
    "a live-grant check this service deliberately never runs). "
    "Machine identities (agents + workloads) only -- human provisioning "
    "drift is not covered."
)


def _tfstate_machine_identity_names(state_path: Path, resource_type: str, name_field: str) -> set[str]:
    if not state_path.exists():
        return set()
    doc = json.loads(state_path.read_text(encoding="utf-8"))
    names = set()
    for resource in doc.get("resources", []):
        if resource["type"] != resource_type or resource["name"] != "machine_identities":
            continue
        for instance in resource.get("instances", []):
            value = instance["attributes"].get(name_field)
            if value:
                names.add(value)
    return names


def _declared_keycloak_names() -> set[str]:
    doc = yaml.safe_load(KEYCLOAK_PROJECTION_PATH.read_text(encoding="utf-8")) or {}
    return {cfg["client_id"] for canonical_id, cfg in doc.get("clients", {}).items()}


def _declared_entra_names() -> set[str]:
    if not ENTRA_PROJECTION_PATH.exists():
        return set()
    doc = yaml.safe_load(ENTRA_PROJECTION_PATH.read_text(encoding="utf-8")) or {}
    return {cfg["display_name"] for canonical_id, cfg in doc.get("app_registrations", {}).items()}


def identity_drift_report() -> dict:
    declared_keycloak = _declared_keycloak_names()
    provisioned_keycloak = _tfstate_machine_identity_names(KEYCLOAK_STATE_PATH, "keycloak_openid_client", "client_id")

    declared_entra = _declared_entra_names()
    provisioned_entra = _tfstate_machine_identity_names(ENTRA_STATE_PATH, "azuread_application", "display_name")

    return {
        "basis": BASIS,
        "keycloak": {
            "declared_only": sorted(declared_keycloak - provisioned_keycloak),
            "provisioned_only": sorted(provisioned_keycloak - declared_keycloak),
            "matched_count": len(declared_keycloak & provisioned_keycloak),
        },
        "entra": {
            "declared_only": sorted(declared_entra - provisioned_entra),
            "provisioned_only": sorted(provisioned_entra - declared_entra),
            "matched_count": len(declared_entra & provisioned_entra),
        },
    }
