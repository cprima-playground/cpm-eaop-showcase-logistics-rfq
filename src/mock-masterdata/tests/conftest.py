import pytest

import mock_masterdata.auth as auth_module

TEST_API_KEY = "test-masterdata-key"


@pytest.fixture(autouse=True)
def _masterdata_api_key(monkeypatch):
    monkeypatch.setenv("MASTERDATA_API_KEY", TEST_API_KEY)
    auth_module._cached_key = None
    yield
    auth_module._cached_key = None
