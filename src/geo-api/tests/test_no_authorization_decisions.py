"""M10 D4: mechanical guard on geo-api's own core invariant -- it computes
a deterministic function of (from, to, mode) and caches the result, it
never makes a Cedar authorization decision. Same spirit and same literal
pattern as mission-control-api's tests/test_no_authorization_decisions.py."""

from pathlib import Path

FORBIDDEN = ("is_authorized", "authorize_and_enforce", "rfq_common.pep.enforce")
PACKAGE_DIR = Path(__file__).resolve().parents[1] / "geo_api"


def test_no_source_file_references_the_authorization_decision_surface():
    """Deliberately a plain literal-substring scan -- no docstring/comment
    carve-out. This package's own source comments must therefore avoid
    spelling out these exact terms even when explaining why they're
    forbidden (paraphrase instead) -- a real constraint on how this
    package documents itself, not a test-tooling gap to work around."""
    violations = []
    for path in PACKAGE_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for term in FORBIDDEN:
            if term in text:
                violations.append(f"{path.relative_to(PACKAGE_DIR.parent)}: found {term!r}")
    assert not violations, "\n".join(violations)
