"""CLI now talks to a *running* mock-fx process (see mock_fx/cli.py's
docstring / rfq_common.http_cli) -- these are real integration tests against
a live server, same skip-gated shape as test_masterdata_integration.py.
`whoami` (rfq_common.cli's base command, no HTTP) stays unconditional.

Rate values aren't asserted exactly (mock-fx is live-by-default -- real ECB
feed on boot/reset, see api.py's module docstring -- so the numbers move day
to day); these check shape/plausibility, not a pinned number.

conftest.py's autouse _fx_api_key fixture forces FX_API_KEY to a fake
offline-test value package-wide (correct for the stub-masterdata unit tests
in test_api.py) -- these live tests override it back to the real Vault-seeded
key, or skip if Vault/the key isn't available."""

from typer.testing import CliRunner
import httpx
import pytest

import mock_fx.auth as auth_module
from mock_fx.cli import app

runner = CliRunner()
FX_URL = "http://127.0.0.1:8001"


def _fx_up() -> bool:
    try:
        return httpx.get(f"{FX_URL}/healthz", timeout=1.0).status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module", autouse=True)
def _skip_if_fx_down():
    if not _fx_up():
        pytest.skip(f"mock-fx not running on {FX_URL}")


@pytest.fixture(autouse=True)
def _real_fx_api_key(monkeypatch):
    r = httpx.get(
        "http://localhost:8200/v1/secret/data/rfq/fx-api-key",
        headers={"X-Vault-Token": "rfq-dev-root"}, timeout=5.0,
    )
    if r.status_code != 200:
        pytest.skip("Vault not running or fx-api-key not seeded")
    monkeypatch.setenv("FX_API_KEY", r.json()["data"]["data"]["value"])
    auth_module._cached_key = None
    yield
    auth_module._cached_key = None


def test_reset_command():
    result = runner.invoke(app, ["reset"])
    assert result.exit_code == 0
    assert '"status": "reset"' in result.output


def test_list_rates_command():
    result = runner.invoke(app, ["list-rates"])
    assert result.exit_code == 0
    assert '"pair": "CNY/EUR"' in result.output


def test_get_rate_command():
    result = runner.invoke(app, ["get-rate", "CNY", "EUR"])
    assert result.exit_code == 0
    assert '"pair": "CNY/EUR"' in result.output


def test_get_rate_unknown_pair_fails():
    result = runner.invoke(app, ["get-rate", "USD", "JPY"])
    assert result.exit_code == 1
    assert "error 404" in result.output


def test_history_command():
    result = runner.invoke(app, ["history", "CNY", "EUR", "--days", "5"])
    assert result.exit_code == 0
    assert result.output.count('"pair":') == 5


def test_convert_command():
    result = runner.invoke(app, ["convert", "100", "CNY", "EUR"])
    assert result.exit_code == 0
    assert '"from_currency": "CNY"' in result.output
    assert '"to_currency": "EUR"' in result.output


def test_stats_command():
    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 0
    assert '"count"' in result.output


def test_whoami_inherited_from_base_cli():
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 0
    assert "system=mock-fx" in result.output
