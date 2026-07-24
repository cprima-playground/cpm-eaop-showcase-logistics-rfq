"""Generic reference-table store (ADR-010) -- one implementation backs all 9
masterdata domains instead of nine bespoke stores. Mirrors mock-fx's FxStore
shape, generalized: load from jsonl, get(code)/list()/reload()."""

from __future__ import annotations

from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel

from .jsonl import load_jsonl

M = TypeVar("M", bound=BaseModel)


class CodeListStore(Generic[M]):
    """A deterministic, jsonl-backed reference table keyed by a code field."""

    def __init__(self, path: str | Path, model: type[M], *, code_field: str = "code"):
        self._path = Path(path)
        self._model = model
        self._code_field = code_field
        self._rows: list[M] = []
        self.reload()

    def reload(self) -> None:
        self._rows = load_jsonl(self._path, self._model)

    def list(self) -> list[M]:
        return list(self._rows)

    def get(self, code: str) -> M | None:
        for row in self._rows:
            if getattr(row, self._code_field) == code:
                return row
        return None

    def __len__(self) -> int:
        return len(self._rows)
