"""M8.6 step 10: traces.py's fail-open behavior (Tempo down must never
500 this endpoint -- observability must never become a synchronous
dependency, rfq_common/observability.py's own hard rule, honored here
too). Live Tempo query behavior is exercised in the real-stack
checkpoint, not here."""

import os

from mission_control_api.traces import search_traces


def test_search_traces_degrades_gracefully_when_tempo_unreachable(monkeypatch):
    monkeypatch.setenv("TEMPO_URL", "http://127.0.0.1:1")  # nothing listens here
    result = search_traces(timeout=1.0)
    assert result["available"] is False
    assert result["traces"] == []
