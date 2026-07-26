"""M10, built directly on M5.5's shared rfq_common.settings contract, same
shape as mission-control-api/settings.py. geo-api's own introspection-auth
client secret (OIDC_CLIENT_SECRET) verifies inbound bearer tokens (D4: authN
yes, Cedar authZ deferred) -- it never calls cedar-agent's real decision
endpoint (see tests/test_no_authorization_decisions.py). Its ONLY other
credential is the shared masterdata-api-key (D4/masterdata_client.py section
of the plan) used to resolve locode coordinates live -- a business-api
transport hop, same posture as every other mock-* consumer, not an identity
credential."""

from __future__ import annotations

import os
from pathlib import Path

from rfq_common.masterdata_client import MasterdataClient
from rfq_common.secrets import SecretsClient
from rfq_common.settings import PrincipalCredentialSettings, ResourceServerSettings

RFQ_ROOT = Path(__file__).resolve().parents[3]
INVENTORY_PATH = RFQ_ROOT / "identity" / "credentials-inventory.yaml"

KEYCLOAK_CLIENT_ID = "geo-api-svc"  # identity/projections/keycloak.yaml: workload.geo-api
EXPECTED_CANONICAL_ID = "workload.geo-api"


def oidc_issuer_url() -> str:
    return ResourceServerSettings.from_env().oidc_issuer_url


def introspection_endpoint() -> str:
    return ResourceServerSettings.from_env().introspection_url


def introspection_client_secret() -> str:
    return PrincipalCredentialSettings.from_env(
        client_id=KEYCLOAK_CLIENT_ID,
        expected_canonical_id=EXPECTED_CANONICAL_ID,
        vault_secret_name="geo-api-svc-client-secret",
        inventory_path=INVENTORY_PATH,
    ).client_secret.get_secret_value()


def masterdata_client() -> MasterdataClient:
    """A business-api transport hop, not an identity credential -- same
    shared masterdata-api-key posture as every other mock-* consumer
    (decision #8), not geo-api's own OIDC identity above."""
    api_key = os.environ.get("MASTERDATA_API_KEY")
    if not api_key:
        api_key = SecretsClient("dev", inventory_path=INVENTORY_PATH).get("masterdata-api-key")
    return MasterdataClient(base_url=os.environ.get("MASTERDATA_URL", "http://127.0.0.1:8003"), api_key=api_key)


def cache_db_path() -> Path:
    return Path(os.environ.get("GEO_API_CACHE_DB", "/data/cache/geo-api-cache.sqlite3"))
