# Themes — passable colorschemes

Design-token packs that re-skin the whole showcase at runtime (no rebuild). Full
model + mechanism: `../systems/theming.md`. ADR: `../decisions/ADR-007-theming.md`.

```text
teaching.theme.json          neutral, high-contrast, SHOWCASE banner on (default)
solarized-light.theme.json   Solarized Light (Ethan Schoonover) — personal preference
corporate-sample.theme.json  grayscale + single accent, banner off — a PLACEHOLDER
```

Personal use: `THEME=solarized-light`.

## Use

```sh
THEME=teaching                       # built-in pack by name (default)
THEME_PATH=/config/acme.theme.json   # your own pack, mounted (takes precedence)
```

Every frontend container reads it; tokens become CSS custom properties per request.
Per-system pages take their accent from `systems.<system-id>`.

## Make your work brand

Copy `corporate-sample.theme.json`, set your palette/logo/name, mount via `THEME_PATH`.

**Governance:** ship neutral defaults here; keep real, trademarked brand assets **out
of this repo** — supply them at runtime on your own infrastructure. Never impersonate
a real organization.
