"""Pure, no-network: registry_roster() derives the 7-entry roster
mechanically from agents/catalog.yaml + interfaces/mcp/tools.yaml,
excluding the `fixture: true` test identity."""

from mission_control_api.registry import registry_roster


def test_roster_excludes_the_test_fixture_agent():
    roster = registry_roster()
    assert "agent.trust-boundary-fixture" not in roster


def test_roster_is_exactly_the_7_real_descriptor_bearing_services():
    roster = registry_roster()
    assert set(roster) == {
        "agent.lane-evaluation", "agent.route-decision", "agent.commercial-normalization",
        "workload.tms-mcp", "workload.rate-mcp", "workload.qms-mcp", "workload.approval-mcp",
    }


def test_no_mock_system_ever_appears_in_the_roster():
    roster = registry_roster()
    assert not any(r.startswith("system.") for r in roster)
