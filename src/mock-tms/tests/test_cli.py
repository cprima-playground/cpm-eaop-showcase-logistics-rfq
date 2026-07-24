from typer.testing import CliRunner

from mock_tms.cli import app

runner = CliRunner()


def test_reset_command():
    result = runner.invoke(app, ["reset"])
    assert result.exit_code == 0
    assert "loaded 13 route(s)" in result.output


def test_routes_command():
    result = runner.invoke(app, ["routes"])
    assert result.exit_code == 0
    assert result.output.count("\n") == 13


def test_feasible_lanes_command():
    result = runner.invoke(app, ["feasible-lanes", "CNSHA-DEMUC"])
    assert result.exit_code == 0
    assert result.output.count("\n") == 7


def test_set_availability_command():
    result = runner.invoke(
        app, ["set-availability", "SHA-HAM-MUC", "unavailable", "--reason", "port congestion"]
    )
    assert result.exit_code == 0
    assert '"status":"unavailable"' in result.output.replace(" ", "")
    assert "port congestion" in result.output


def test_set_availability_unknown_route():
    result = runner.invoke(app, ["set-availability", "NOPE", "unavailable"])
    assert result.exit_code == 1
    assert "no route" in result.output


def test_whoami_inherited():
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 0
    assert "system=mock-tms" in result.output
