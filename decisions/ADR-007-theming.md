# ADR-007 — Passable theming

**Status:** accepted.
**Context:** the showcase must run in **teaching** (neutral) and **at work** (your
brand) from the same images, and each mock system must stay visually distinct.

## Decision

We will theme via **design tokens rendered as CSS custom properties**, selected at
runtime by a **passed colorscheme** — no rebuild to switch.

- **Two tiers:** a global **brand pack** (`themes/*.theme.json`) + a **per-system
  accent** derived from `theme.systems.<id>` (distinct-but-cohesive).
- **Runtime:** the shared Jinja base emits `:root { --color-…: … }` per request;
  Tailwind/components use `var(--color-…)`. One image, many themes.
- **Passing:** `THEME_PATH` (mounted file) > `THEME` (built-in name) > default
  (`teaching`). Env var on every frontend container (compose + Cloud Run).
- **Validation:** a Pydantic token model in `rfq_common` validates a pack on load.
- **Built-ins shipped:** `teaching`, `solarized-light` (Ethan Schoonover, open
  palette), `corporate-sample` (placeholder).

Spec: `../systems/theming.md`.

## Governance

Ship **neutral** defaults only. The "at work" pack is **user-supplied**; real,
trademarked brand assets stay **out of the repo** (mounted at runtime). Never
impersonate a real organization. The `SHOWCASE` banner defaults on.

## Alternatives rejected

- **Build-time Tailwind theme** — needs a rebuild per brand; breaks one-image parity.
- **Per-system hard-coded colors** — can't be re-skinned for context; superseded by
  tier-2 accents from the brand pack.

## Consequences

- `rfq_common` owns the token model + the CSS-var renderer + pack loader.
- Frontends take their per-system accent from the loaded pack, not constants.
- `deploy` passes `THEME`/`THEME_PATH` to every frontend service.
