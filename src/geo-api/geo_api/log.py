"""Custom TRACE level (below DEBUG) + shared configure_logging() for geo-api.

Every module just calls `logging.getLogger(__name__)` as usual -- Python's
logging registry is global, so configure_logging() (called once, from
cli.py, at process start) applies retroactively to loggers created by
imports that ran before it.

Added for real diagnosability during the ocean-leg 502/native-crash
investigation: ocean_astar.py already had log.debug() calls throughout, but
nothing ever configured a handler or level for them, so they were silently
dropped -- `docker logs` never showed a single one, regardless of GEO_API_LOG_LEVEL.
"""

from __future__ import annotations

import logging
import os

TRACE = 5
logging.addLevelName(TRACE, "TRACE")


def _trace(self: logging.Logger, message: str, *args, **kwargs) -> None:
    if self.isEnabledFor(TRACE):
        self._log(TRACE, message, args, **kwargs)


logging.Logger.trace = _trace  # type: ignore[attr-defined]


def get_logger(name: str) -> logging.Logger:
    """Thin wrapper over logging.getLogger -- exists so callers get the
    `.trace()` method typed/discoverable without needing to know it was
    monkey-patched on; plain `logging.getLogger(__name__)` works identically."""
    return logging.getLogger(name)


def configure_logging() -> None:
    """GEO_API_LOG_LEVEL (default INFO) controls verbosity as a deploy-time
    knob -- accepts TRACE/DEBUG/INFO/WARNING/ERROR. force=True because
    uvicorn (or another import) may already have called basicConfig with its
    own handler/format before this runs."""
    level_name = os.environ.get("GEO_API_LOG_LEVEL", "INFO").upper()
    level = TRACE if level_name == "TRACE" else getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        force=True,
    )
    logging.getLogger("geo_api").setLevel(level)
