"""The masterdata source -- 9 reference domains (ADR-010)."""

from .api import build_app
from .store import DOMAINS, MasterdataStore

__all__ = ["build_app", "MasterdataStore", "DOMAINS"]
