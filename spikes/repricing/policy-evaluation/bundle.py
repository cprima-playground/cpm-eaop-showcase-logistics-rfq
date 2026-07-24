"""The showcase's authorization bundle: policies + obligation-id resolution.

Mirrors cpm-eaop src/spike/model/authz_bundle.py exactly (same @id/@obligations
regex parsing of policies.cedar). Cedar never sees obligations; this module is the
mapping point from determining-policy-ids -> obligation IDS (not full payloads —
the scenario `then` blocks only assert obligation ids).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

RFQ_ROOT = Path(__file__).resolve().parents[3]
POLICIES_CEDAR = RFQ_ROOT / "authorization" / "policies.cedar"

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


@lru_cache(maxsize=1)
def _bundle() -> dict:
    text = POLICIES_CEDAR.read_text(encoding="utf-8")
    policies, oblig_by_policy = [], {}
    for block in _split_policies(text):
        id_match = _ID.search(block)
        if not id_match:
            raise ValueError(f"policy block missing @id:\n{block[:80]}")
        pid = id_match.group(1)
        policies.append({"id": pid, "content": block})
        obl = _OBLIG.search(block)
        oblig_by_policy[pid] = [o.strip() for o in obl.group(1).split(",")] if obl else []
    return {"policies": policies, "oblig_by_policy": oblig_by_policy}


def policies() -> list[dict]:
    """[{id, content}] for the policy store."""
    return _bundle()["policies"]


def resolve_obligation_ids(determining_policy_ids: list[str]) -> list[str]:
    """Determining (satisfied permit) policy ids -> union of obligation ids."""
    b = _bundle()
    out: list[str] = []
    for pid in determining_policy_ids:
        for oid in b["oblig_by_policy"].get(pid, []):
            if oid not in out:
                out.append(oid)
    return out
