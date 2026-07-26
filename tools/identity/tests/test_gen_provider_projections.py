from pathlib import Path

import pytest
import yaml

from tools.identity.gen_entra import EntraGenError, generate_entra_input
from tools.identity.gen_keycloak import KeycloakGenError, generate_keycloak_input, generate_oid
from tools.identity.validator import validate_identity

ROOT = Path(__file__).resolve().parents[3]
KEYCLOAK_PROJECTION = ROOT / "identity" / "projections" / "keycloak.yaml"
ENTRA_PROJECTION = ROOT / "identity" / "projections" / "entra.yaml"


def _real_model():
    return validate_identity(
        ROOT / "identity" / "actors.yaml",
        ROOT / "identity" / "groups.yaml",
        ROOT / "business" / "departments.yaml",
        ROOT / "business" / "job-titles.yaml",
    )


def test_keycloak_gen_covers_every_human_and_machine_identity():
    model = _real_model()
    out = generate_keycloak_input(model, KEYCLOAK_PROJECTION)
    humans = [p for p in model.principals if p.kind == "human"]
    machines = [p for p in model.principals if p.kind in ("agent", "workload")]
    assert len(out["users"]) == len(humans)
    assert len(out["clients"]) == len(machines)
    assert len(out["groups"]) == len(model.groups)


def test_keycloak_gen_attributes_match_known_live_shape():
    model = _real_model()
    out = generate_keycloak_input(model, KEYCLOAK_PROJECTION)
    mona = next(u for u in out["users"] if u["username"] == "mona.commercial")
    assert mona["attributes"]["region"] == "EMEA"
    assert mona["attributes"]["manager"] == "diane.delgado"
    assert mona["attributes"]["approval_limit_eur_cents"] == "1000000"
    # oid_overrides preserves the exact live GUID for zero-diff (M3.2a) --
    # NOT generate_oid("mona.commercial"), which would differ.
    assert mona["attributes"]["oid"] == "8e41c2b0-0000-4000-9000-000000000011"

    wei = next(u for u in out["users"] if u["username"] == "human.wei.planning")
    assert wei["attributes"]["oid"] == generate_oid("human.wei.planning")


def test_generate_oid_is_deterministic_not_random():
    assert generate_oid("mona.commercial") == generate_oid("mona.commercial")
    assert generate_oid("mona.commercial") != generate_oid("sam.pricing")


def test_keycloak_gen_fails_loud_on_missing_client_projection(tmp_path):
    model = _real_model()
    empty_projection = tmp_path / "keycloak.yaml"
    empty_projection.write_text(yaml.safe_dump({"realm": "rfq", "clients": {}}), encoding="utf-8")
    with pytest.raises(KeycloakGenError):
        generate_keycloak_input(model, empty_projection)


def test_entra_gen_upns_use_tenant_domain():
    model = _real_model()
    out = generate_entra_input(model, ENTRA_PROJECTION)
    mona = next(u for u in out["users"] if u["upn"] == "mona.commercial@rpapubhotmail.onmicrosoft.com")
    assert mona["attributes"]["approval_limit_eur_cents"] == "1000000"


def test_entra_and_keycloak_business_attributes_match():
    """M3.4's canonical-principal parity is at the resolved-principal
    level, not raw-claim level (plan decision #4) -- `oid` legitimately
    differs per IdP (Keycloak's may be an override, Entra's is always
    generated), same as real Keycloak/Entra `sub`/`oid`/`tid` never
    matching. Only the actual business attributes must match."""
    model = _real_model()
    kc = generate_keycloak_input(model, KEYCLOAK_PROJECTION)
    entra = generate_entra_input(model, ENTRA_PROJECTION)

    def business_attrs(attrs):
        return {k: v for k, v in attrs.items() if k != "oid"}

    kc_attrs = {u["username"]: business_attrs(u["attributes"]) for u in kc["users"]}
    entra_attrs = {u["upn"].split("@")[0]: business_attrs(u["attributes"]) for u in entra["users"]}
    assert kc_attrs == entra_attrs


def test_entra_gen_fails_loud_on_missing_app_registration(tmp_path):
    model = _real_model()
    empty_projection = tmp_path / "entra.yaml"
    empty_projection.write_text(
        yaml.safe_dump({"tenant_domain": "example.onmicrosoft.com", "app_registrations": {}}), encoding="utf-8"
    )
    with pytest.raises(EntraGenError):
        generate_entra_input(model, empty_projection)
