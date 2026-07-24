"""Human SSO login -- Authorization Code + PKCE against the dev Keycloak realm
(infra/keycloak/). Adapted from cpm-eaop's app/spike/controlpanel/sso.py:
same hand-rolled PKCE/session approach, no OAuth library. Differs in one way:
claims come from verifying the access token via rfq_common.verify.verify()
(signature/issuer/audience checked) rather than trusting /userinfo's response
un-verified, then resolve_principal() turns claims into a typed Principal --
this is the first thing in RfQ to exercise identity/claims-contract.md for
real.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import urllib.parse

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from rfq_common.identity import resolve_principal
from rfq_common.verify import fetch_jwks, verify_with_jwks

from . import config

router = APIRouter()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _pkce_pair() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


@router.get("/login")
def login(request: Request):
    issuer = config.keycloak_issuer_url()
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)

    request.session["pkce_verifier"] = verifier
    request.session["oauth_state"] = state

    redirect_uri = f"{config.public_base_url()}/callback"
    params = {
        "client_id": config.keycloak_client_id(),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid profile email",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return RedirectResponse(f"{issuer}/protocol/openid-connect/auth?{urllib.parse.urlencode(params)}")


@router.get("/callback")
def callback(request: Request, code: str, state: str):
    if state != request.session.get("oauth_state"):
        return RedirectResponse("/?error=state_mismatch")

    issuer = config.keycloak_issuer_url()
    redirect_uri = f"{config.public_base_url()}/callback"
    ssl_context = config.caddy_ssl_context()

    token_resp = httpx.post(
        f"{issuer}/protocol/openid-connect/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": config.keycloak_client_id(),
            "client_secret": config.keycloak_client_secret(),
            "code_verifier": request.session.pop("pkce_verifier"),
        },
        timeout=15,
        verify=ssl_context,
    )
    token_resp.raise_for_status()
    access_token = token_resp.json()["access_token"]

    jwks = fetch_jwks(f"{issuer}/protocol/openid-connect/certs", verify=config.caddy_ca_bundle())
    verified = verify_with_jwks(
        access_token, jwks, issuer=issuer, audience=config.keycloak_client_id(),
    )
    principal = resolve_principal(verified.claims)
    request.session["principal"] = principal.model_dump()
    request.session["id_token"] = token_resp.json().get("id_token")
    return RedirectResponse("/")


@router.get("/logout")
def logout(request: Request):
    """Clears our session AND ends the Keycloak SSO session (RP-initiated
    logout, id_token_hint) -- without this, Keycloak's own session survives
    our /logout, so the next /login silently re-authenticates as the same
    user instead of showing the login form (see KNOWN-ISSUES.md #8)."""
    issuer = config.keycloak_issuer_url()
    id_token = request.session.pop("id_token", None)
    request.session.clear()

    if id_token is None:
        return RedirectResponse("/")

    params = {"id_token_hint": id_token, "post_logout_redirect_uri": config.public_base_url()}
    return RedirectResponse(f"{issuer}/protocol/openid-connect/logout?{urllib.parse.urlencode(params)}")
