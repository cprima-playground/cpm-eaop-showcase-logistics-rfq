"""Deterministic FX rate history -- generated in Python at store-load time,
never committed as static fixture files (the 2 real fixtures, today/yesterday,
stay the sole source of truth for the project's canonical documented
breakout -- see fixtures/fx/README or store.py). First real consumer of
`rfq_common.clock.seeded_rng()` in mock-fx.

Band width is deliberately kept under the D4 threshold (`fx_variance_pct_x10
> 20`, i.e. 2.0% -- authorization/policies.cedar) so 28 days of generated
"normal" history read as market noise, never themselves a false breakout.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

from rfq_common.models import ExchangeRate

BAND_AMPLITUDE = 0.012  # +-1.2%, an oscillating "seasonal" component
NOISE_AMPLITUDE = 0.004  # +-0.4% random jitter per day
# BAND_AMPLITUDE + NOISE_AMPLITUDE = 1.6% max single-point deviation from
# anchor -- comfortably under the 2.0% D4 threshold by construction.


def generate_history(
    pair: str,
    *,
    anchor_rate: float,
    before: datetime,
    days: int,
    rng: random.Random,
    rate_type: str = "corporate",
    source: str = "corporate-fx-service-generated",
) -> list[ExchangeRate]:
    """`days` synthetic points ending the day before `before` (exclusive),
    oldest first. Deterministic given the same `rng` state -- callers seed
    once per reload() via rfq_common.clock.seeded_rng()."""
    points = []
    for k in range(days, 0, -1):
        observed_at = before - timedelta(days=k)
        seasonal = BAND_AMPLITUDE * math.sin(2 * math.pi * (days - k) / 10)
        jitter = NOISE_AMPLITUDE * (rng.random() * 2 - 1)
        rate = round(anchor_rate * (1 + seasonal + jitter), 6)
        points.append(ExchangeRate(
            pair=pair,
            rate=rate,
            rate_type=rate_type,
            source=source,
            observed_at=observed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            valid_until=(observed_at + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            rate_ref=f"FX-GEN-{observed_at.strftime('%Y%m%d')}-{pair.replace('/', '-')}",
        ))
    return points


def generate_staircase(
    pair: str,
    *,
    anchor_rate: float,
    before: datetime,
    steps: int,
    step_pct: float,
    rng: random.Random,
    rate_type: str = "corporate",
    source: str = "corporate-fx-service-generated",
) -> list[ExchangeRate]:
    """A `steps`-day sequence where each individual day-over-day move is
    `step_pct` (well under the 2.0% D4 threshold alone), but the CUMULATIVE
    move across all steps deliberately exceeds it -- proves the generator
    can produce a breakout pattern a naive "check yesterday-vs-today"
    detector would miss, without wiring a scenario pack/policy for it (see
    KNOWN-ISSUES.md -- blocked on the not-yet-built scenario runner).
    Standalone/pure -- not called by FxStore.reload()."""
    points = []
    rate = anchor_rate
    for k in range(steps, 0, -1):
        observed_at = before - timedelta(days=k)
        # Same direction every step (accumulate, don't cancel) -- rng only
        # jitters the exact magnitude slightly, never flips the sign.
        jittered_step = step_pct * (1 + 0.15 * (rng.random() * 2 - 1))
        rate = round(rate * (1 + jittered_step), 6)
        points.append(ExchangeRate(
            pair=pair,
            rate=rate,
            rate_type=rate_type,
            source=source,
            observed_at=observed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            valid_until=(observed_at + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            rate_ref=f"FX-STAIR-{observed_at.strftime('%Y%m%d')}-{pair.replace('/', '-')}",
        ))
    return points
