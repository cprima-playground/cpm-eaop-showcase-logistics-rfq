"""CLI now talks to a *running* mock-masterdata process (see
mock_masterdata/cli.py's docstring / rfq_common.http_cli) -- these are real
integration tests against a live server, same skip-gated shape as
test_masterdata_integration.py in the other systems. `domains`/`whoami`
(static/no HTTP) stay unconditional.

conftest.py's autouse _masterdata_api_key fixture forces MASTERDATA_API_KEY
to a fake offline-test value package-wide (correct for test_api.py) -- these
live tests override it back to the real Vault-seeded key, or skip if
Vault/the key isn't available."""

from typer.testing import CliRunner
import httpx
import pytest

import mock_masterdata.auth as auth_module
from mock_masterdata.cli import app

runner = CliRunner()
MASTERDATA_URL = "http://127.0.0.1:8003"


def _masterdata_up() -> bool:
    try:
        return httpx.get(f"{MASTERDATA_URL}/healthz", timeout=1.0).status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module", autouse=True)
def _skip_if_masterdata_down():
    if not _masterdata_up():
        pytest.skip(f"mock-masterdata not running on {MASTERDATA_URL}")


@pytest.fixture(autouse=True)
def _real_masterdata_api_key(monkeypatch):
    r = httpx.get(
        "http://localhost:8200/v1/secret/data/rfq/masterdata-api-key",
        headers={"X-Vault-Token": "rfq-dev-root"}, timeout=5.0,
    )
    if r.status_code != 200:
        pytest.skip("Vault not running or masterdata-api-key not seeded")
    monkeypatch.setenv("MASTERDATA_API_KEY", r.json()["data"]["data"]["value"])
    auth_module._cached_key = None
    yield
    auth_module._cached_key = None


def test_domains_command_lists_9():
    result = runner.invoke(app, ["domains"])
    assert result.exit_code == 0
    assert len(result.output.strip().splitlines()) == 9


def test_list_command():
    result = runner.invoke(app, ["list", "currencies"])
    assert result.exit_code == 0
    assert "EUR" in result.output


def test_get_command():
    result = runner.invoke(app, ["get", "locations", "CNSHA"])
    assert result.exit_code == 0
    assert "Shanghai" in result.output


def test_get_unknown_code_fails():
    result = runner.invoke(app, ["get", "currencies", "XXX"])
    assert result.exit_code == 1
    assert "error 404" in result.output


def test_unknown_domain_fails():
    result = runner.invoke(app, ["list", "not-a-domain"])
    assert result.exit_code == 1


def test_reset_command():
    result = runner.invoke(app, ["reset"])
    assert result.exit_code == 0
    assert '"status": "reset"' in result.output


def test_stats_command():
    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 0
    assert '"total"' in result.output
    assert '"by_domain"' in result.output


def test_whoami_inherited():
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 0
    assert "system=mock-masterdata" in result.output
