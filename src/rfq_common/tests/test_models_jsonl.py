from pathlib import Path

from rfq_common.jsonl import load_jsonl, read_jsonl, write_jsonl
from rfq_common.models import RFQ, InternalPrincipal, Quote


def test_rfq_model_defaults():
    rfq = RFQ(rfq_id="RFQ-1001", contracted_lane="SHA-HAM-MUC")
    assert rfq.status == "draft"
    assert rfq.system_of_record == "crm"


def test_quote_status_is_the_human_decision():
    q = Quote(quote_id="Q-1001", version=2, status="approval_required", margin_pct_x10=50)
    assert q.status == "approval_required"
    q2 = q.model_copy(update={"status": "approved"})
    assert q2.status == "approved"


def test_internal_principal_kind_literal():
    p = InternalPrincipal(id="commercial-normalization-agent", kind="agent", active=True)
    assert p.kind == "agent"
    assert p.member_of == []


def test_jsonl_roundtrip(tmp_path: Path):
    path = tmp_path / "rfqs.jsonl"
    rfqs = [
        RFQ(rfq_id="RFQ-1001", contracted_lane="SHA-HAM-MUC"),
        RFQ(rfq_id="RFQ-1002", contracted_lane="SHA-RTM-MUC"),
    ]
    write_jsonl(path, rfqs)

    raw = read_jsonl(path)
    assert len(raw) == 2
    assert raw[0]["rfq_id"] == "RFQ-1001"

    loaded = load_jsonl(path, RFQ)
    assert loaded == rfqs


def test_jsonl_skips_blank_lines(tmp_path: Path):
    path = tmp_path / "x.jsonl"
    path.write_text('{"rfq_id": "RFQ-1"}\n\n{"rfq_id": "RFQ-2"}\n', encoding="utf-8")
    rows = read_jsonl(path)
    assert len(rows) == 2
