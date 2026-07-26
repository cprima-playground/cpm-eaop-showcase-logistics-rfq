"""M5.5: ServiceResolver -- EnvironmentServiceResolver today, verifying
it does exactly what direct os.environ.get(...) reads did before, just
behind one interface (so a future RegistryServiceResolver can be dropped
in without touching calling code)."""

from __future__ import annotations

import pytest

from rfq_common.service_resolver import EnvironmentServiceResolver, ServiceResolutionError


def test_resolves_configured_dependency(monkeypatch):
    monkeypatch.setenv("LANE_EVAL_AGENT_URL", "http://127.0.0.1:8204")
    resolver = EnvironmentServiceResolver({"agent.lane-evaluation": "LANE_EVAL_AGENT_URL"})
    assert resolver.resolve("agent.lane-evaluation") == "http://127.0.0.1:8204"


def test_unconfigured_canonical_id_raises(monkeypatch):
    resolver = EnvironmentServiceResolver({"agent.lane-evaluation": "LANE_EVAL_AGENT_URL"})
    with pytest.raises(ServiceResolutionError):
        resolver.resolve("agent.route-decision")


def test_configured_but_unset_env_var_raises(monkeypatch):
    monkeypatch.delenv("LANE_EVAL_AGENT_URL", raising=False)
    resolver = EnvironmentServiceResolver({"agent.lane-evaluation": "LANE_EVAL_AGENT_URL"})
    with pytest.raises(ServiceResolutionError):
        resolver.resolve("agent.lane-evaluation")


def test_only_configured_dependencies_are_resolvable():
    """A process's mapping should only list what it actually calls --
    this test documents that an empty mapping resolves nothing, i.e. the
    resolver never silently reaches for an env var it wasn't told about."""
    resolver = EnvironmentServiceResolver({})
    with pytest.raises(ServiceResolutionError):
        resolver.resolve("agent.anything")
