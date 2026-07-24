from pathlib import Path

from rfq_common.codelist import CodeListStore
from rfq_common.jsonl import write_jsonl
from rfq_common.models import Currency, Party


def test_generic_store_loads_get_list(tmp_path: Path):
    path = tmp_path / "currencies.jsonl"
    write_jsonl(path, [
        Currency(code="EUR", name="Euro", minor_unit=2, symbol="€"),
        Currency(code="JPY", name="Japanese Yen", minor_unit=0, symbol="¥"),
    ])
    store = CodeListStore(path, Currency)
    assert len(store) == 2
    assert store.get("JPY").minor_unit == 0
    assert store.get("XXX") is None
    assert {c.code for c in store.list()} == {"EUR", "JPY"}


def test_generic_store_custom_code_field(tmp_path: Path):
    path = tmp_path / "parties.jsonl"
    write_jsonl(path, [Party(party_id="ACME", name="ACME Corp", kind="customer")])
    store = CodeListStore(path, Party, code_field="party_id")
    assert store.get("ACME").name == "ACME Corp"


def test_generic_store_reload_picks_up_changes(tmp_path: Path):
    path = tmp_path / "eq.jsonl"
    from rfq_common.models import Equipment
    write_jsonl(path, [Equipment(code="20GP", name="20ft General Purpose", type="container")])
    store = CodeListStore(path, Equipment)
    assert len(store) == 1
    write_jsonl(path, [
        Equipment(code="20GP", name="20ft General Purpose", type="container"),
        Equipment(code="40HC", name="40ft High Cube", type="container"),
    ])
    store.reload()
    assert len(store) == 2
