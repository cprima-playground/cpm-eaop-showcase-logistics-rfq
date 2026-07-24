"""Offline tests -- parse_history()/load_history_from_file() never touch the
network; fetch_history()'s HTTP call itself is exercised only implicitly
(via store.py's monkeypatched tests), never here."""

from pathlib import Path

import pytest

from mock_fx import ecb_client

SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
<gesmes:subject>Reference rates</gesmes:subject>
<gesmes:Sender><gesmes:name>European Central Bank</gesmes:name></gesmes:Sender>
<Cube>
<Cube time="2026-07-24"><Cube currency="USD" rate="1.1377"/><Cube currency="JPY" rate="186.38"/><Cube currency="GBP" rate="0.85388"/><Cube currency="CNY" rate="7.7047"/><Cube currency="CHF" rate="0.9302"/></Cube>
<Cube time="2026-07-23"><Cube currency="USD" rate="1.1392"/><Cube currency="JPY" rate="186.23"/><Cube currency="GBP" rate="0.85318"/><Cube currency="CNY" rate="7.7127"/><Cube currency="CHF" rate="0.931"/></Cube>
</Cube>
</gesmes:Envelope>"""


def test_parse_history_returns_oldest_first_restricted_to_requested_currencies():
    days = ecb_client.parse_history(SAMPLE_XML, ("USD", "GBP", "JPY", "CNY"))
    assert [d for d, _ in days] == ["2026-07-23", "2026-07-24"]
    assert days[-1][1] == {"USD": 1.1377, "JPY": 186.38, "GBP": 0.85388, "CNY": 7.7047}
    assert "CHF" not in days[-1][1]  # only the requested currencies come back


def test_parse_history_rejects_malformed_xml():
    with pytest.raises(ecb_client.EcbUnavailableError):
        ecb_client.parse_history(b"not xml at all", ("USD",))


def test_parse_history_rejects_missing_cube_structure():
    with pytest.raises(ecb_client.EcbUnavailableError):
        ecb_client.parse_history(b"<root/>", ("USD",))


def test_parse_history_rejects_empty_result_for_requested_currencies():
    with pytest.raises(ecb_client.EcbUnavailableError):
        ecb_client.parse_history(SAMPLE_XML, ("ZZZ",))


def test_load_history_from_file_reads_a_local_copy(tmp_path):
    path = tmp_path / "ecb-hist-cache.xml"
    path.write_bytes(SAMPLE_XML)
    days = ecb_client.load_history_from_file(path, ("CNY",))
    assert days == [("2026-07-23", {"CNY": 7.7127}), ("2026-07-24", {"CNY": 7.7047})]


def test_load_history_from_file_missing_file_raises():
    with pytest.raises(ecb_client.EcbUnavailableError):
        ecb_client.load_history_from_file(Path("/no/such/file.xml"), ("USD",))
