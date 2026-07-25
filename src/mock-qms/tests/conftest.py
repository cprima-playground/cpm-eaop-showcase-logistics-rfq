"""Package-root conftest -- cross-subdirectory-safe constants ONLY. No
autouse stubbing/monkeypatching lives here: unit/, integration/, and
business/ each need a genuinely different environment (offline stubs vs.
real live services), and pytest applies each subdirectory's own conftest.py
on top of this one -- keeping this file inert is what stops unit/'s stubs
from silently leaking into integration/business's live-service tests."""

TEST_API_KEY = "test-qms-key"
TEST_SESSION_SECRET = "test-qms-session-secret"
