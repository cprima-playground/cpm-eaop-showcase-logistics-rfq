from typer.testing import CliRunner

from mock_rate.cli import app

runner = CliRunner()


def test_reset_command():
    result = runner.invoke(app, ["reset"])
    assert result.exit_code == 0
    assert "loaded 16 rate(s)" in result.output


def test_rates_command():
    result = runner.invoke(app, ["rates"])
    assert result.exit_code == 0
    assert result.output.count("\n") == 16


def test_get_rate_command():
    result = runner.invoke(app, ["get-rate", "SHA-HAM-MUC"])
    assert result.exit_code == 0
    assert "COSCO" in result.output


def test_get_rate_command_unknown_fails():
    result = runner.invoke(app, ["get-rate", "NOPE"])
    assert result.exit_code == 1


def test_whoami_inherited():
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 0
    assert "system=mock-rate" in result.output
