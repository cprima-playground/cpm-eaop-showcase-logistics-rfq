from rfq_common.identity import Principal, resolve_principal


def test_human_claims_resolve_to_human():
    p = resolve_principal({
        "sub": "793c1ccd-3ce2-4959-bd14-3925b387220b",
        "tid": "rfq-dev-tenant",
        "oid": "8e41c2b0-0000-4000-9000-000000000001",
        "groups": ["/Ops"],
        "roles": ["ops-viewer"],
    })
    assert p.kind == "human"
    assert p.oid == "8e41c2b0-0000-4000-9000-000000000001"
    assert p.tid == "rfq-dev-tenant"
    assert p.groups == ["/Ops"]
    assert p.has_role("ops-viewer")
    assert not p.has_role("admin")


def test_no_human_claims_resolves_to_service():
    p = resolve_principal({"sub": "some-client-id", "scope": "read"})
    assert p.kind == "service"
    assert p.oid is None
    assert p.tid is None
    assert p.groups is None
    assert p.roles is None


def test_no_role_claim_has_role_is_false():
    p = resolve_principal({"tid": "rfq-dev-tenant", "sub": "bob"})
    assert p.kind == "human"
    assert p.has_role("ops-viewer") is False


def test_active_defaults_true_but_honors_claim():
    assert resolve_principal({"tid": "x", "sub": "a"}).active is True
    assert resolve_principal({"tid": "x", "sub": "a", "active": False}).active is False


def test_principal_is_a_pydantic_model():
    p = Principal(kind="human", id="x")
    assert p.model_dump()["kind"] == "human"
