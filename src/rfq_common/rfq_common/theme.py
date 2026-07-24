"""Theme token model + CSS-custom-property renderer (ADR-007). Validates a theme
pack on load (systems/theming.md's schema) and renders it to CSS custom properties
at runtime -- one image, many themes, no rebuild to switch.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Brand(BaseModel):
    model_config = ConfigDict(extra="ignore")
    app_prefix: str
    logo: str
    favicon: str


class Banner(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str = ""
    show: bool = True


class Colors(BaseModel):
    model_config = ConfigDict(extra="ignore")
    primary: str
    secondary: str
    accent: str
    success: str
    warning: str
    danger: str
    bg: str
    surface: str
    text: str
    muted: str


class Typography(BaseModel):
    model_config = ConfigDict(extra="ignore")
    font: str
    scale: Literal["comfortable", "compact"] = "comfortable"


class ThemePack(BaseModel):
    """A validated design-token pack (themes/*.theme.json)."""

    model_config = ConfigDict(extra="ignore")

    name: str
    mode: Literal["light", "dark", "auto"] = "light"
    brand: Brand
    banner: Banner = Field(default_factory=Banner)
    colors: Colors
    systems: dict[str, str] = Field(default_factory=dict)
    typography: Typography
    density: Literal["comfortable", "compact"] = "comfortable"

    @classmethod
    def from_path(cls, path: str | Path) -> "ThemePack":
        return cls.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def load_theme(*, themes_dir: str | Path, theme_path: str | None = None,
                theme_name: str | None = None) -> ThemePack:
    """Precedence (systems/theming.md): THEME_PATH file > THEME built-in name >
    default 'teaching'. `themes_dir` is the caller's themes/ folder (this library
    is IdP/repo-location agnostic, per ADR-006 -- callers own their paths)."""
    theme_path = theme_path or os.environ.get("THEME_PATH")
    if theme_path:
        return ThemePack.from_path(theme_path)

    name = theme_name or os.environ.get("THEME") or "teaching"
    return ThemePack.from_path(Path(themes_dir) / f"{name}.theme.json")


def render_css_vars(pack: ThemePack, *, system_id: str | None = None) -> str:
    """Render a pack (optionally with a per-system accent override) to CSS custom
    properties for the shared Jinja base layout's :root block."""
    lines = [
        f"--color-primary: {pack.colors.primary};",
        f"--color-secondary: {pack.colors.secondary};",
        f"--color-accent: {pack.colors.accent};",
        f"--color-success: {pack.colors.success};",
        f"--color-warning: {pack.colors.warning};",
        f"--color-danger: {pack.colors.danger};",
        f"--color-bg: {pack.colors.bg};",
        f"--color-surface: {pack.colors.surface};",
        f"--color-text: {pack.colors.text};",
        f"--color-muted: {pack.colors.muted};",
        f"--font: {pack.typography.font};",
    ]
    if system_id and system_id in pack.systems:
        lines.append(f"--color-accent: {pack.systems[system_id]};")  # per-system override, tier 2
    return ":root {\n  " + "\n  ".join(lines) + "\n}"
