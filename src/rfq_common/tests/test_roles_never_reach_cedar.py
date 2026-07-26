"""Regression guard for identity/README.md's hard rule: `roles` claims are
UI-gating only, never a canonical authorization fact. Static check, not a
live one -- greps for any PDPClient.authorize()/context dict that mentions
"roles", across the whole repo. Passes trivially today (no production
PDPClient caller exists yet, per the implementation plan's own finding);
becomes meaningful once M4a adds real callers -- if someone wires a
`roles` claim into a Cedar `context` then, this starts failing and forces
a conscious decision, not a silent regression.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_AUTHORIZE_CALL_WITH_ROLES = re.compile(r"\.authorize\s*\([^)]*roles", re.DOTALL)


def _python_files():
    for path in ROOT.glob("src/**/*.py"):
        if ".venv" in path.parts or "tests" in path.parts:
            continue
        yield path


def test_no_authorize_call_passes_roles_anywhere():
    offenders = []
    for path in _python_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if _AUTHORIZE_CALL_WITH_ROLES.search(text):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        f"found .authorize(...) call(s) referencing 'roles' in {offenders} -- "
        "roles claims are UI-gating only, see identity/README.md's hard rule"
    )
