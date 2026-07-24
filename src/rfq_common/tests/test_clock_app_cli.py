from pathlib import Path

from urllib.parse import unquote

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from rfq_common.app import create_app
from rfq_common.cli import create_cli
from rfq_common.clock import age_seconds, now, seed
from rfq_common.theme import ThemePack

RFQ_ROOT = Path(__file__).resolve().parents[3]
THEMES_DIR = RFQ_ROOT / "themes"


# --- clock ---------------------------------------------------------------------

def test_now_uses_pinned_clock(monkeypatch):
    monkeypatch.setenv("NOW", "2026-07-24T09:00:00Z")
    n = now()
    assert n.year == 2026 and n.month == 7 and n.day == 24 and n.hour == 9


def test_now_falls_back_to_real_time(monkeypatch):
    monkeypatch.delenv("NOW", raising=False)
    n = now()
    assert n.year >= 2026  # sanity: real clock, not a fixed past date


def test_age_seconds_matches_pinned_clock(monkeypatch):
    monkeypatch.setenv("NOW", "2026-07-24T09:00:00Z")
    assert age_seconds("2026-07-24T08:48:00Z") == 720  # matches scenario 01's fx_age_seconds


def test_seed_default_and_env(monkeypatch):
    monkeypatch.delenv("SEED", raising=False)
    assert seed() == 42
    monkeypatch.setenv("SEED", "7")
    assert seed() == 7


# --- base FastAPI app ------------------------------------------------------------

def test_app_healthz():
    app = create_app("Mock FX")
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["system"] == "Mock FX"


def test_app_theme_css_and_banner_header():
    pack = ThemePack.from_path(THEMES_DIR / "teaching.theme.json")
    app = create_app("Mock CPQ", system_id="cpq", theme_pack=pack)
    client = TestClient(app)

    css = client.get("/_theme.css")
    assert css.status_code == 200
    assert "--color-accent" in css.text

    health = client.get("/healthz")
    assert unquote(health.headers.get("X-Showcase-Banner", "")) == "SHOWCASE — teaching"


def test_app_no_theme_pack_is_safe():
    app = create_app("Mock TMS")
    client = TestClient(app)
    r = client.get("/_theme.css")
    assert r.status_code == 200


# --- base Typer CLI --------------------------------------------------------------

def test_cli_whoami(monkeypatch):
    monkeypatch.setenv("NOW", "2026-07-24T09:00:00Z")
    monkeypatch.setenv("SEED", "42")
    runner = CliRunner()
    result = runner.invoke(create_cli("mock-fx"), ["whoami"])
    assert result.exit_code == 0
    assert "seed=42" in result.output
    assert "2026-07-24T09:00:00" in result.output


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(create_cli("mock-fx", version="1.2.3"), ["version"])
    assert result.exit_code == 0
    assert "1.2.3" in result.output
