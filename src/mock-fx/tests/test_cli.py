from typer.testing import CliRunner

from mock_fx.cli import app

runner = CliRunner()


def test_reset_command():
    result = runner.invoke(app, ["reset"])
    assert result.exit_code == 0
    assert "loaded 30 rate snapshot(s)" in result.output


def test_get_rate_command():
    result = runner.invoke(app, ["get-rate", "CNY", "EUR"])
    assert result.exit_code == 0
    assert "0.1194" in result.output


def test_get_rate_command_point_in_time():
    result = runner.invoke(app, ["get-rate", "CNY", "EUR", "--effective-at", "2026-07-23T12:00:00Z"])
    assert result.exit_code == 0
    assert "0.1226" in result.output


def test_get_rate_command_unknown_pair_fails():
    result = runner.invoke(app, ["get-rate", "USD", "JPY"])
    assert result.exit_code == 1


def test_whoami_inherited_from_base_cli():
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 0
    assert "system=mock-fx" in result.output
