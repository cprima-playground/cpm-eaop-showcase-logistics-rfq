# Theming — a passable colorscheme for the whole showcase

Goal: run the *same* showcase in **teaching** (neutral) and **at work** (your brand)
by **passing a colorscheme**, without touching code or rebuilding images.

## Two tiers

1. **Brand pack (global)** — the passed colorscheme: palette · fonts · logo · app
   name · banner. One pack = one context (`teaching`, `corporate-sample`, your own).
2. **Per-system accent** — each mock system derives a distinct hue from the brand
   pack (`theme.systems.<id>`), so systems stay **distinguishable yet cohesive** under
   whichever brand is loaded. (Replaces the earlier hard-coded per-system colors.)

## Mechanism — design tokens → CSS custom properties (runtime)

- A **theme pack** is a JSON of **design tokens** (`themes/*.theme.json`).
- The shared Jinja base layout emits them as **CSS custom properties** per request:
  `:root { --color-primary: …; --color-accent: …; --font: …; }`.
- Tailwind utilities/components reference `var(--color-…)`. → **switching theme needs
  no Tailwind rebuild**; one image serves every theme.
- Per-system pages set `--color-accent` from `theme.systems[<system-id>]`.
- **Modes**: `light | dark | auto` (`prefers-color-scheme`); a pack supplies both.

## How it's passed

| Precedence | Source | Example |
| --- | --- | --- |
| 1 | `THEME_PATH` (mounted file) | `THEME_PATH=/config/acme.theme.json` |
| 2 | `THEME` (built-in pack name) | `THEME=teaching` |
| 3 | default | `teaching` |

Env var on every frontend container (compose + Cloud Run). Mount your work pack as a
file (or Secret/Config); select a built-in by name.

## Token schema (validated in `rfq_common`)

```jsonc
{
  "name": "…",
  "mode": "light|dark|auto",
  "brand":  { "app_prefix": "…", "logo": "<path|data-uri>", "favicon": "…" },
  "banner": { "text": "SHOWCASE", "show": true },
  "colors": { "primary": "#…", "secondary": "#…", "accent": "#…",
              "success": "#…", "warning": "#…", "danger": "#…",
              "bg": "#…", "surface": "#…", "text": "#…", "muted": "#…" },
  "systems": { "crm": "#…", "tms": "#…", "rate": "#…",
               "qms": "#…", "fx": "#…", "workflow": "#…" },
  "typography": { "font": "…", "scale": "comfortable|compact" },
  "density": "comfortable|compact"
}
```

A Pydantic model validates a pack on load (required keys, valid hex) — a bad pack
fails fast, not silently.

## Governance (important)

- **Never impersonate a real organization.** Ship **neutral** defaults; the "at work"
  pack is **user-supplied**. Do **not** commit a real company's trademarked logo,
  name, or exact brand colors into this repo.
- The `SHOWCASE` banner is on by default (teaching); a work pack may hide it — that is
  the user's choice on their own infrastructure, not an impersonation baked into the repo.

## Built-in packs

- `themes/teaching.theme.json` — neutral, high-contrast, `SHOWCASE` banner on.
- `themes/corporate-sample.theme.json` — a **placeholder** grayscale+single-accent
  pack; copy it to make your own work brand (`themes/README.md`).

See ADR-007 (`../decisions/ADR-007-theming.md`).
