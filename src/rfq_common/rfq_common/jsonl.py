"""Generic jsonl fixture loader. Mirrors cpm-eaop's data/identity/*.jsonl seeding
pattern: one record per line, deterministic, git-diffable."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

M = TypeVar("M", bound=BaseModel)


def read_jsonl(path: Path) -> list[dict]:
    """Read a jsonl file into plain dicts. Blank lines are skipped."""
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def load_jsonl(path: Path, model: type[M]) -> list[M]:
    """Read a jsonl file and validate each line against a Pydantic model."""
    return [model.model_validate(row) for row in read_jsonl(path)]


def write_jsonl(path: Path, rows: Iterable[dict | BaseModel]) -> None:
    """Write rows (dicts or Pydantic models) as one JSON object per line."""
    lines = []
    for row in rows:
        data = row.model_dump(mode="json") if isinstance(row, BaseModel) else row
        lines.append(json.dumps(data, ensure_ascii=False))
    Path(path).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
