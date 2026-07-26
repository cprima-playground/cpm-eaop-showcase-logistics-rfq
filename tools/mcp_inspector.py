"""Print the live connection data needed by MCP Inspector.

Run from the repository root after starting the local authenticated MCP spike:

    python tools/mcp_inspector.py

The script obtains a short-lived test token from the local Keycloak realm using
the existing qms-web client and the repository's dev user. It prints the token
because the operator needs to paste it into MCP Inspector; it never prints the
client secret.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import ssl
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
TERRAFORM_DIR = ROOT / "infra" / "keycloak" / "terraform"


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def terraform_client_secret() -> str:
    result = subprocess.run(
        ["terraform", "output", "-raw", "qms_web_client_secret"],
        cwd=TERRAFORM_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Could not read qms_web_client_secret from Terraform. "
            "Run terraform init/apply in infra/keycloak/terraform first."
        )
    secret = result.stdout.strip()
    if not secret:
        raise RuntimeError("Terraform returned an empty qms_web_client_secret.")
    return secret


def post_form(url: str, values: dict[str, str]) -> dict:
    request = Request(
        url,
        data=urlencode(values).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=15, context=tls_context()) as response:
            return json.loads(response.read().decode())
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"Keycloak returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach Keycloak at {url}: {exc.reason}") from exc


def check_mcp(endpoint: str, token: str, correlation_id: str) -> dict:
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "mcp-inspector-helper", "version": "0.1.0"},
        },
    }
    request = Request(
        endpoint,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "X-Correlation-Id": correlation_id,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=15, context=tls_context()) as response:
            content = response.read().decode(errors="replace")
            return {
                "http_status": response.status,
                "content_type": response.headers.get("Content-Type"),
                "correlation_id": response.headers.get("X-Correlation-Id"),
                "mcp_session_id": response.headers.get("MCP-Session-Id"),
                "body_preview": content[:300],
            }
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        return {
            "http_status": exc.code,
            "content_type": exc.headers.get("Content-Type"),
            "correlation_id": exc.headers.get("X-Correlation-Id"),
            "mcp_session_id": exc.headers.get("MCP-Session-Id"),
            "body_preview": detail[:300],
        }
    except URLError as exc:
        return {"error": f"Could not reach MCP endpoint: {exc.reason}"}


def tls_context() -> ssl.SSLContext | None:
    ca_cert = os.environ.get(
        "MCP_CADDY_CA_CERT",
        str(ROOT / "infra" / "caddy" / "root.crt"),
    )
    if Path(ca_cert).exists():
        return ssl.create_default_context(cafile=ca_cert)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--copy", action="store_true", help="Copy the Authorization header to the system clipboard")
    parser.add_argument("--no-token", action="store_true", help="Do not print the bearer token")
    parser.add_argument("--debug", action="store_true", help="Print safe token/clipboard diagnostics")
    parser.add_argument("--no-check", action="store_true", help="Do not call the MCP initialize endpoint")
    parser.add_argument("--endpoint", default=env("MCP_INSPECTOR_ENDPOINT", "http://localhost:8091/mcp"))
    parser.add_argument("--username", default=env("MCP_TEST_USERNAME", "mona.commercial"))
    parser.add_argument("--password", default=env("MCP_TEST_PASSWORD", "rfq-dev-user"))
    args = parser.parse_args()

    keycloak_base = env(
        "MCP_KEYCLOAK_BASE_URL",
        "https://keycloak.rfq-showcase.localhost",
    )
    token_endpoint = f"{keycloak_base}/realms/rfq/protocol/openid-connect/token"
    client_id = env("MCP_INTROSPECTION_CLIENT_ID", "qms-web")
    correlation_id = f"inspector-{uuid.uuid4()}"

    try:
        secret = terraform_client_secret()
        token_response = post_form(
            token_endpoint,
            {
                "grant_type": "password",
                "client_id": client_id,
                "client_secret": secret,
                "username": args.username,
                "password": args.password,
                "scope": "openid",
            },
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    token = token_response.get("access_token")
    if not token:
        print("ERROR: Keycloak response did not contain an access_token.", file=sys.stderr)
        return 1

    if args.debug:
        print(f"DEBUG: token_received=True token_length={len(token)} token_segments={token.count('.') + 1}")

    result = {
        "transport": "Streamable HTTP",
        "endpoint": args.endpoint,
        "authorization": f"Bearer {token}",
        "headers": {
            "Authorization": f"Bearer {token}",
            "X-Correlation-Id": correlation_id,
        },
        "do_not_enter_manually": [
            "MCP-Protocol-Version",
            "MCP-Session-Id",
            "Accept",
            "Content-Type",
        ],
        "next_actions": [
            "Paste endpoint into MCP Inspector as a Streamable HTTP connection.",
            "Use the bearer token in the Authorization field, or use the headers object.",
            "Invoke echo_authenticated with message='hello from Inspector'.",
            "Read resource demo://authenticated-contract.",
        ],
    }

    authorization_header = result["authorization"]
    if args.copy:
        if os.name == "nt":
            copy_result = subprocess.run(
                ["clip.exe"],
                input=authorization_header + "\r\n",
                text=True,
                check=False,
            )
            if copy_result.returncode != 0:
                raise RuntimeError(f"clip.exe failed with exit code {copy_result.returncode}")
            result["clipboard"] = "Authorization header copied to the Windows clipboard."
            if args.debug:
                print(
                    "DEBUG: clipboard_command=clip.exe "
                    f"returncode={copy_result.returncode} header_length={len(authorization_header)}"
                )
        elif shutil.which("pbcopy"):
            subprocess.run(["pbcopy"], input=authorization_header, text=True, check=True)
            result["clipboard"] = "Authorization header copied to the macOS clipboard."
        elif shutil.which("xclip"):
            subprocess.run(["xclip", "-selection", "clipboard"], input=authorization_header, text=True, check=True)
            result["clipboard"] = "Authorization header copied to the X clipboard."
        else:
            result["clipboard"] = "No supported clipboard command was found."

    if not args.no_check:
        result["initialize_check"] = check_mcp(args.endpoint, token, correlation_id)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Transport: {result['transport']}")
        print(f"Endpoint:  {result['endpoint']}")
        print(f"Correlation ID: {correlation_id}")
        print()
        if args.copy:
            print(result["clipboard"])
        if not args.no_token:
            print("Authorization header:")
            print(result["authorization"])
        print()
        print("Additional header:")
        print(f"X-Correlation-Id: {correlation_id}")
        print()
        print("MCP Inspector actions:")
        for action in result["next_actions"]:
            print(f"- {action}")
        if "initialize_check" in result:
            print()
            print("Initialize check:")
            print(json.dumps(result["initialize_check"], indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
