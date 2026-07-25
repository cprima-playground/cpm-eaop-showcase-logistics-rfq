"""CLI now talks to a *running* mock-rate process (see mock_rate/cli.py's
docstring / rfq_common.http_cli) -- these are real integration tests against
a live server, same skip-gated shape as test_masterdata_integration.py.
`whoami`/`version` (rfq_common.cli's base commands, no HTTP) stay unconditional.

conftest.py's autouse _rate_api_key fixture forces RATE_API_KEY to a fake
offline-test value package-wide (correct for the stub-masterdata unit tests
in test_api.py) -- these live tests override it back to the real Vault-seeded
key, or skip if Vault/the key isn't available."""

from typer.testing import CliRunner
import httpx
import pytest

import mock_rate.auth as auth_module
from mock_rate.cli import app

runner = CliRunner()
RATE_URL = "http://127.0.0.1:8005"


def _rate_up() -> bool:
    try:
        return httpx.get(f"{RATE_URL}/healthz", timeout=1.0).status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module", autouse=True)
def _skip_if_rate_down():
    if not _rate_up():
        pytest.skip(f"mock-rate not running on {RATE_URL}")


@pytest.fixture(autouse=True)
def _real_rate_api_key(monkeypatch):
    r = httpx.get(
        "http://localhost:8200/v1/secret/data/rfq/rate-api-key",
        headers={"X-Vault-Token": "rfq-dev-root"}, timeout=5.0,
    )
    if r.status_code != 200:
        pytest.skip("Vault not running or rate-api-key not seeded")
    monkeypatch.setenv("RATE_API_KEY", r.json()["data"]["data"]["value"])
    auth_module._cached_key = None
    yield
    auth_module._cached_key = None


def test_reset_command():
    result = runner.invoke(app, ["reset"])
    assert result.exit_code == 0
    assert '"status": "reset"' in result.output


def test_rates_command():
    result = runner.invoke(app, ["rates"])
    assert result.exit_code == 0
    assert result.output.count('"route_id":') == 16


def test_get_rate_command():
    result = runner.invoke(app, ["get-rate", "SHA-HAM-MUC"])
    assert result.exit_code == 0
    assert '"carrier_id": "COSCO"' in result.output


def test_get_rate_unknown_route_404():
    result = runner.invoke(app, ["get-rate", "NOPE"])
    assert result.exit_code == 1
    assert "error 404" in result.output


def test_get_surcharges_command():
    result = runner.invoke(app, ["get-surcharges", "SHA-HAM-MUC"])
    assert result.exit_code == 0
    assert '"surcharges": 5100' in result.output


def test_stats_command():
    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 0
    assert '"count"' in result.output


def test_whoami_inherited():
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 0
    assert "system=mock-rate" in result.output
