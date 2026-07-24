"""Parse a policies.cedar TEXT into individual policies + obligation-id
resolution. Same @id/@obligations regex parsing as cpm-eaop's authz_bundle.py,
generalized to take text/path rather than a hardcoded repo location -- any mock
system package can point this at its own policies.cedar."""

from __future__ import annotations

import re
from pathlib import Path

_ID = re.compile(r'@id\("([^"]+)"\)')
_OBLIG = re.compile(r'@obligations\("([^"]+)"\)')


def _split_policies(text: str) -> list[str]:
    blocks, cur = [], []
    for line in text.splitlines():
        stripped = line.strip()
        if not cur and (stripped == "" or stripped.startswith("//")):
            continue
        cur.append(line)
        if stripped.endswith(";"):
            blocks.append("\n".join(cur))
            cur = []
    return blocks


class PolicyBundle:
    """policies() for the policy store; resolve_obligation_ids() for the PEP."""

    def __init__(self, text: str):
        self._policies: list[dict] = []
        self._oblig_by_policy: dict[str, list[str]] = {}
        for block in _split_policies(text):
            id_match = _ID.search(block)
            if not id_match:
                raise ValueError(f"policy block missing @id:\n{block[:80]}")
            pid = id_match.group(1)
            self._policies.append({"id": pid, "content": block})
            obl = _OBLIG.search(block)
            self._oblig_by_policy[pid] = [o.strip() for o in obl.group(1).split(",")] if obl else []

    @classmethod
    def from_path(cls, path: str | Path) -> "PolicyBundle":
        return cls(Path(path).read_text(encoding="utf-8"))

    def policies(self) -> list[dict]:
        """[{id, content}] for the policy store."""
        return self._policies

    def resolve_obligation_ids(self, determining_policy_ids: list[str]) -> list[str]:
        """Determining (satisfied permit) policy ids -> union of obligation ids."""
        out: list[str] = []
        for pid in determining_policy_ids:
            for oid in self._oblig_by_policy.get(pid, []):
                if oid not in out:
                    out.append(oid)
        return out
