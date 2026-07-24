from mock_masterdata.store import DOMAINS, MasterdataStore, fixtures_dir


def test_all_9_domains_load():
    store = MasterdataStore(fixtures_dir())
    assert set(store.stores) == set(DOMAINS)
    assert len(DOMAINS) == 9


def test_real_unlocode_migrated():
    store = MasterdataStore(fixtures_dir())
    sha = store.get("locations", "CNSHA")
    assert sha is not None
    assert sha.name == "Shanghai"
    assert sha.type == "seaport"


def test_currency_minor_units():
    store = MasterdataStore(fixtures_dir())
    assert store.get("currencies", "JPY").minor_unit == 0
    assert store.get("currencies", "EUR").minor_unit == 2


def test_incoterms_2020_count():
    store = MasterdataStore(fixtures_dir())
    assert len(store.list("incoterms")) == 11  # the 11 Incoterms 2020 rules


def test_party_customer_and_carrier():
    store = MasterdataStore(fixtures_dir())
    assert store.get("parties", "ACME").kind == "customer"
    assert store.get("parties", "COSCO").kind == "carrier"


def test_commodity_dangerous_goods_flag():
    store = MasterdataStore(fixtures_dir())
    battery = store.get("commodities", "8506.50")
    assert battery.dangerous_goods is True
    assert battery.dg_class == "9"


def test_unknown_code_returns_none():
    store = MasterdataStore(fixtures_dir())
    assert store.get("currencies", "XXX") is None


def test_reload_all_domains():
    store = MasterdataStore(fixtures_dir())
    before = {d: len(s) for d, s in store.stores.items()}
    store.reload()
    after = {d: len(s) for d, s in store.stores.items()}
    assert before == after
