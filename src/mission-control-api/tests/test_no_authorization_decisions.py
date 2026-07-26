"""M8.4: mechanical guard on Mission Control's own core invariant --
it observes and reports, it never decides. No source file under
mission_control_api/ may reference the real authorization-decision
surface (is_authorized, authorize_and_enforce, rfq_common.pep.enforce).
Same spirit as src/qms-mcp/tests/test_adr002_disjointness.py's
mechanical-not-by-inspection check."""

from pathlib import Path

FORBIDDEN = ("is_authorized", "authorize_and_enforce", "rfq_common.pep.enforce")
PACKAGE_DIR = Path(__file__).resolve().parents[1] / "mission_control_api"


def test_no_source_file_references_the_authorization_decision_surface():
    """Deliberately a plain literal-substring scan, same mechanical-not-
    by-inspection simplicity as test_adr002_disjointness.py -- no
    docstring/comment carve-out. This package's own source comments must
    therefore avoid spelling out these exact terms even when explaining
    why they're forbidden (paraphrase instead, e.g. "the real decision
    endpoint" not "/v1/is_authorized") -- a real constraint on how this
    package documents itself, not a test-tooling gap to work around."""
    violations = []
    for path in PACKAGE_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for term in FORBIDDEN:
            if term in text:
                violations.append(f"{path.relative_to(PACKAGE_DIR.parent)}: found {term!r}")
    assert not violations, "\n".join(violations)
