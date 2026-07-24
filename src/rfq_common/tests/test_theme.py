"""Proves the theme model validates the REAL theme packs (themes/*.theme.json)
and the CSS-var renderer produces a usable :root block, per ADR-007."""

from pathlib import Path

import pytest

from rfq_common.theme import ThemePack, load_theme, render_css_vars

RFQ_ROOT = Path(__file__).resolve().parents[3]
THEMES_DIR = RFQ_ROOT / "themes"


@pytest.mark.parametrize("name", ["teaching", "solarized-light", "corporate-sample"])
def test_real_theme_packs_validate(name):
    pack = ThemePack.from_path(THEMES_DIR / f"{name}.theme.json")
    assert pack.colors.primary.startswith("#")
    assert pack.typography.font


def test_load_theme_precedence_env_name(monkeypatch):
    monkeypatch.delenv("THEME_PATH", raising=False)
    monkeypatch.setenv("THEME", "solarized-light")
    pack = load_theme(themes_dir=THEMES_DIR)
    assert pack.name == "Solarized Light"


def test_load_theme_defaults_to_teaching(monkeypatch):
    monkeypatch.delenv("THEME_PATH", raising=False)
    monkeypatch.delenv("THEME", raising=False)
    pack = load_theme(themes_dir=THEMES_DIR)
    assert pack.name == "Teaching"


def test_load_theme_path_takes_precedence_over_name(monkeypatch):
    monkeypatch.setenv("THEME", "teaching")
    pack = load_theme(themes_dir=THEMES_DIR, theme_path=str(THEMES_DIR / "solarized-light.theme.json"))
    assert pack.name == "Solarized Light"


def test_render_css_vars_includes_all_core_colors():
    pack = ThemePack.from_path(THEMES_DIR / "teaching.theme.json")
    css = render_css_vars(pack)
    assert css.startswith(":root {")
    for var in ("--color-primary", "--color-accent", "--color-bg", "--font"):
        assert var in css


def test_render_css_vars_per_system_accent_overrides():
    pack = ThemePack.from_path(THEMES_DIR / "teaching.theme.json")
    css_crm = render_css_vars(pack, system_id="crm")
    css_fx = render_css_vars(pack, system_id="fx")
    # each system's override is the LAST --color-accent line -> distinct per system
    assert css_crm.count("--color-accent") == 2
    assert css_crm != css_fx
