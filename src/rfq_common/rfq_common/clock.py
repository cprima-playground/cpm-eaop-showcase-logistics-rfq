"""Clock + seed helpers for deterministic runs (RUNNING.md). `NOW` pinned via env
is the load-bearing piece -- FX freshness (policies D1/D2) is `now - observed_at`,
and on wall-clock the same fixture drifts and can flip allow<->deny between demos.
"""

from __future__ import annotations

import os
import random
from datetime import datetime, timezone

DEFAULT_SEED = 42


def now() -> datetime:
    """The pinned scenario clock if NOW is set (ISO 8601, e.g.
    2026-07-24T09:00:00Z), else real UTC time."""
    raw = os.environ.get("NOW")
    if raw:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def age_seconds(observed_at: str | datetime) -> int:
    """Seconds between `now()` and an observed_at timestamp -- the fact
    fx-rate.read/route-cost.normalize gate on (context.fx_age_seconds)."""
    if isinstance(observed_at, str):
        observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    return int((now() - observed_at).total_seconds())


def seed() -> int:
    """The pinned RNG seed (SEED env), else the repo-wide default (42, per
    systems/rate/fixtures/cost-model.md)."""
    return int(os.environ.get("SEED", DEFAULT_SEED))


def seeded_rng() -> random.Random:
    """A Random instance seeded per seed() -- byte-stable fixture generation."""
    return random.Random(seed())
