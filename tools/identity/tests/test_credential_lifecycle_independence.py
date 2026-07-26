"""Machine credentials are a provider/runtime concern, never a canonical
identity fact (identity/README.md's "Machine credentials are a runtime
concern" section, added after M3.3's live Entra export showed 7 generated
application passwords with expiration dates).

This module enforces the invariant, not just documents it: no generator
output may contain or depend on any secret/credential value, so rotating
one later can't silently become an identity event (canonical_id, can_call,
Cedar relationships, or client_id/display_name changing as a side effect).
"""

from __future__ import annotations

from pathlib import Path

from tools.identity.gen_cedar_entities import generate_cedar_entities
from tools.identity.gen_entra import generate_entra_input
from tools.identity.gen_keycloak import generate_keycloak_input
from tools.identity.validator import validate_identity

ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "agents" / "catalog.yaml"
KEYCLOAK_PROJECTION = ROOT / "identity" / "projections" / "keycloak.yaml"
ENTRA_PROJECTION = ROOT / "identity" / "projections" / "entra.yaml"

_CREDENTIAL_FIELD_NAMES = {
    "secret", "client_secret", "password", "value", "credential",
    "end_date", "expires", "expiry", "rotation",
}


def _real_model():
    return validate_identity(
        ROOT / "identity" / "actors.yaml",
        ROOT / "identity" / "groups.yaml",
        ROOT / "business" / "departments.yaml",
        ROOT / "business" / "job-titles.yaml",
    )


def _walk_keys(obj) -> set[str]:
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            keys |= _walk_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            keys |= _walk_keys(item)
    return keys


def test_keycloak_gen_output_carries_no_credential_field():
    model = _real_model()
    out = generate_keycloak_input(model, KEYCLOAK_PROJECTION)
    keys = {k.lower() for k in _walk_keys(out)}
    assert not (keys & _CREDENTIAL_FIELD_NAMES), keys & _CREDENTIAL_FIELD_NAMES


def test_entra_gen_output_carries_no_credential_field():
    model = _real_model()
    out = generate_entra_input(model, ENTRA_PROJECTION)
    keys = {k.lower() for k in _walk_keys(out)}
    assert not (keys & _CREDENTIAL_FIELD_NAMES), keys & _CREDENTIAL_FIELD_NAMES


def test_cedar_entity_gen_output_carries_no_credential_field():
    model = _real_model()
    entities = generate_cedar_entities(model, CATALOG_PATH)
    keys = {k.lower() for k in _walk_keys(entities)}
    assert not (keys & _CREDENTIAL_FIELD_NAMES), keys & _CREDENTIAL_FIELD_NAMES


def test_machine_identity_outputs_are_deterministic():
    """No credential/timestamp dependency anywhere in the machine-identity
    path: calling the generators twice, with nothing changed, must produce
    byte-identical output. If a future change made client_id/canonical_id/
    can_call depend on rotation-adjacent state (e.g. a timestamp), this
    would start failing."""
    model = _real_model()
    kc_a = generate_keycloak_input(model, KEYCLOAK_PROJECTION)
    kc_b = generate_keycloak_input(model, KEYCLOAK_PROJECTION)
    assert kc_a == kc_b

    entra_a = generate_entra_input(model, ENTRA_PROJECTION)
    entra_b = generate_entra_input(model, ENTRA_PROJECTION)
    assert entra_a == entra_b

    cedar_a = generate_cedar_entities(model, CATALOG_PATH)
    cedar_b = generate_cedar_entities(model, CATALOG_PATH)
    assert cedar_a == cedar_b


def test_machine_identity_client_ids_stable_regardless_of_credential_state():
    """The provider client_id/display_name (the second layer -- 'provider
    application/client') is derived only from identity/actors.yaml +
    projection config, never from a credential -- proven by construction:
    generate_keycloak_input/generate_entra_input take no credential/secret
    argument at all, so there is no code path by which rotating a secret
    could change either."""
    import inspect

    from tools.identity import gen_entra, gen_keycloak

    kc_params = set(inspect.signature(gen_keycloak.generate_keycloak_input).parameters)
    entra_params = set(inspect.signature(gen_entra.generate_entra_input).parameters)
    assert kc_params == {"model", "projection_path"}
    assert entra_params == {"model", "projection_path"}
