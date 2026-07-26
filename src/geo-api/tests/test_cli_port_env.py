"""SERVICE_HOST/SERVICE_PORT are canonical; A2A_HOST/A2A_PORT are
legacy-compat fallbacks -- same pattern every other service in this repo
follows, asserted here so geo-api doesn't silently drift."""

from geo_api.cli import _resolve_host_port


def test_service_port_wins_over_a2a_port(monkeypatch):
    monkeypatch.setenv("SERVICE_PORT", "9001")
    monkeypatch.setenv("A2A_PORT", "9002")
    _, port = _resolve_host_port()
    assert port == 9001


def test_a2a_port_is_a_fallback_when_service_port_unset(monkeypatch):
    monkeypatch.delenv("SERVICE_PORT", raising=False)
    monkeypatch.setenv("A2A_PORT", "9002")
    _, port = _resolve_host_port()
    assert port == 9002


def test_hardcoded_default_applies_when_neither_is_set(monkeypatch):
    monkeypatch.delenv("SERVICE_PORT", raising=False)
    monkeypatch.delenv("A2A_PORT", raising=False)
    _, port = _resolve_host_port()
    assert port == 8400
