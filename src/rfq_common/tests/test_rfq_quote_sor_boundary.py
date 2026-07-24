"""business/decisions.md's "SoR boundary: RFQ vs Quote" resolved in code:
Quote.status is the primary fact (QMS), RFQ.status's accepted/rejected/expired
are a derived projection (CRM), never independently settable."""

from rfq_common.models import derive_rfq_status_from_quote


def test_quote_accepted_derives_rfq_accepted():
    assert derive_rfq_status_from_quote("accepted") == "accepted"


def test_quote_rejected_derives_rfq_rejected():
    assert derive_rfq_status_from_quote("rejected") == "rejected"


def test_quote_withdrawn_derives_rfq_rejected():
    """withdrawn is a QMS-internal action (the quote itself was pulled back),
    but from the RFQ case's point of view the outcome reads the same as a
    rejection -- no quote is on the table anymore."""
    assert derive_rfq_status_from_quote("withdrawn") == "rejected"


def test_quote_expired_derives_rfq_expired():
    assert derive_rfq_status_from_quote("expired") == "expired"


def test_non_terminal_quote_statuses_derive_nothing():
    """The case is still open -- there is nothing yet for RFQ to reflect."""
    for status in ("draft", "priced", "approval_required", "approved", "published", "revise"):
        assert derive_rfq_status_from_quote(status) is None
