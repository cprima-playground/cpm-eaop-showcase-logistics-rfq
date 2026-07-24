"""Offline JWT/JWKS verification tests -- a locally generated RSA keypair, no
network, no live IdP (mirrors cpm-eaop's golden-fixture discipline)."""

import time

import jwt
import pytest
from jwt.algorithms import RSAAlgorithm
from cryptography.hazmat.primitives.asymmetric import rsa

from rfq_common.verify import VerificationError, verify_with_jwks

ISSUER = "http://keycloak.localhost/realms/rfq"
AUDIENCE = "rfq-showcase"


@pytest.fixture(scope="module")
def keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    jwk = RSAAlgorithm.to_jwk(public_key, as_dict=True)
    jwk["kid"] = "test-key-1"
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return private_key, {"keys": [jwk]}


def _sign(private_key, *, iss=ISSUER, aud=AUDIENCE, exp_delta=3600, **extra):
    now = int(time.time())
    payload = {"iss": iss, "aud": aud, "iat": now, "exp": now + exp_delta, "sub": "commercial-normalization-agent", **extra}
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": "test-key-1"})


def test_verify_with_jwks_accepts_valid_token(keypair):
    private_key, jwks = keypair
    token = _sign(private_key, azp="commercial-normalization-agent-svc", scope="agent")
    result = verify_with_jwks(token, jwks, issuer=ISSUER, audience=AUDIENCE)
    assert result.issuer == ISSUER
    assert result.audience == AUDIENCE
    assert result.claims["azp"] == "commercial-normalization-agent-svc"


def test_verify_with_jwks_rejects_wrong_issuer(keypair):
    private_key, jwks = keypair
    token = _sign(private_key, iss="http://evil.example/realms/rfq")
    with pytest.raises(VerificationError):
        verify_with_jwks(token, jwks, issuer=ISSUER, audience=AUDIENCE)


def test_verify_with_jwks_rejects_wrong_audience(keypair):
    private_key, jwks = keypair
    token = _sign(private_key, aud="someone-else")
    with pytest.raises(VerificationError):
        verify_with_jwks(token, jwks, issuer=ISSUER, audience=AUDIENCE)


def test_verify_with_jwks_rejects_expired_token(keypair):
    private_key, jwks = keypair
    token = _sign(private_key, exp_delta=-10)
    with pytest.raises(VerificationError):
        verify_with_jwks(token, jwks, issuer=ISSUER, audience=AUDIENCE)


def test_verify_with_jwks_rejects_tampered_signature(keypair):
    _, jwks = keypair
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = _sign(other_key)  # signed with a DIFFERENT key than what's in jwks
    with pytest.raises(VerificationError):
        verify_with_jwks(token, jwks, issuer=ISSUER, audience=AUDIENCE)


def test_verify_with_jwks_rejects_non_jwt():
    with pytest.raises(VerificationError):
        verify_with_jwks("not-a-jwt", {"keys": []}, issuer=ISSUER, audience=AUDIENCE)
