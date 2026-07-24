from typer.testing import CliRunner

from mock_masterdata.cli import app

runner = CliRunner()


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


def test_unknown_domain_fails():
    result = runner.invoke(app, ["list", "not-a-domain"])
    assert result.exit_code == 1


def test_reset_command():
    result = runner.invoke(app, ["reset"])
    assert result.exit_code == 0
    assert "'locations': 21" in result.output


def test_whoami_inherited():
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 0
    assert "system=mock-masterdata" in result.output
