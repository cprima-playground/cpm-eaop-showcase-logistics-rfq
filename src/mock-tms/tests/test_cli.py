"""CLI now talks to a *running* mock-tms process (see mock_tms/cli.py's
docstring / rfq_common.http_cli) -- these are real integration tests against
a live server, same skip-gated shape as test_masterdata_integration.py.
`whoami`/`version` (rfq_common.cli's base commands, no HTTP) stay unconditional.

conftest.py's autouse _tms_api_key fixture forces TMS_API_KEY to a fake
offline-test value package-wide (correct for the stub-masterdata unit tests
in test_api.py) -- these live tests override it back to the real Vault-seeded
key, or skip if Vault/the key isn't available."""

from typer.testing import CliRunner
import httpx
import pytest

import mock_tms.auth as auth_module
from mock_tms.cli import app

runner = CliRunner()
TMS_URL = "http://127.0.0.1:8004"


def _tms_up() -> bool:
    try:
        return httpx.get(f"{TMS_URL}/healthz", timeout=1.0).status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module", autouse=True)
def _skip_if_tms_down():
    if not _tms_up():
        pytest.skip(f"mock-tms not running on {TMS_URL}")


@pytest.fixture(autouse=True)
def _real_tms_api_key(monkeypatch):
    r = httpx.get(
        "http://localhost:8200/v1/secret/data/rfq/tms-api-key",
        headers={"X-Vault-Token": "rfq-dev-root"}, timeout=5.0,
    )
    if r.status_code != 200:
        pytest.skip("Vault not running or tms-api-key not seeded")
    monkeypatch.setenv("TMS_API_KEY", r.json()["data"]["data"]["value"])
    auth_module._cached_key = None
    yield
    auth_module._cached_key = None


def test_reset_command():
    result = runner.invoke(app, ["reset"])
    assert result.exit_code == 0
    assert '"status": "reset"' in result.output


def test_routes_command():
    result = runner.invoke(app, ["routes"])
    assert result.exit_code == 0
    assert result.output.count('"id":') == 17


def test_get_route_command():
    result = runner.invoke(app, ["get-route", "SHA-HAM-MUC"])
    assert result.exit_code == 0
    assert '"id": "SHA-HAM-MUC"' in result.output


def test_feasible_lanes_command():
    result = runner.invoke(app, ["feasible-lanes", "CNSHA-DEMUC"])
    assert result.exit_code == 0
    assert result.output.count('"id":') == 8


def test_set_availability_command():
    result = runner.invoke(
        app, ["set-availability", "SHA-HAM-MUC", "unavailable", "--reason", "port congestion"]
    )
    assert result.exit_code == 0
    assert '"status": "unavailable"' in result.output
    assert "port congestion" in result.output

    # real mutation on the live server -- get-availability sees it too
    verify = runner.invoke(app, ["get-availability", "SHA-HAM-MUC"])
    assert '"status": "unavailable"' in verify.output

    # restore the server's baseline for other tests/processes sharing it
    runner.invoke(app, ["reset"])


def test_set_availability_unknown_route():
    result = runner.invoke(app, ["set-availability", "NOPE", "unavailable"])
    assert result.exit_code == 1
    assert "no route" in result.output


def test_stats_command():
    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 0
    assert '"count"' in result.output


def test_whoami_inherited():
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 0
    assert "system=mock-tms" in result.output
