"""Cedar PDP runtime client — authorization only. Identical shape to cpm-eaop's
src/spike/model/pdp_client.py (verified against it): a versioned, canonical
AuthorizationDecision carrying only the raw Cedar result -- no platform concepts.
Reused as-is here since it's already fully generic (base_url + uid strings)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx


@dataclass
class AuthorizationDecision:
    effect: str  # "allow" | "deny"
    determining_policies: list[str] = field(default_factory=list)
    diagnostics: list = field(default_factory=list)
    version: int = 1


class PDPClient:
    """Thin HTTP client over cedar-agent `POST /v1/is_authorized`."""

    def __init__(self, base_url: str | None = None, timeout: float = 5.0):
        # 8280, not 8180 -- see pdp/admin.py's _base_url() for why.
        self._url = (base_url or os.environ.get("CEDAR_AGENT_URL", "http://localhost:8280")) + "/v1/is_authorized"
        self._timeout = timeout

    def authorize(self, principal: str, action: str, resource: str,
                  context: dict | None = None, *,
                  additional_entities: list[dict] | None = None) -> AuthorizationDecision:
        """principal/action/resource are Cedar entity uids, e.g.
        `Agentic::Principal::"alice"`, `Agentic::Action::"agent.invoke"`.

        `additional_entities` (optional): request-scoped entity records
        (rfq_common.pdp.entities.entity()'s shape) supplied ONLY for this
        one call -- cedar-agent's own `/v1/is_authorized` supports this
        directly (verified against the real running sidecar), distinct
        from the persisted entity store DataAdmin.put() writes to. Use
        this for a resource fact that changes per request (e.g. a Quote's
        current status, fetched live from mock-qms) -- never push such
        facts into the persisted store from request-handling code."""
        body = {"principal": principal, "action": action, "resource": resource,
                "context": context or {}}
        if additional_entities:
            body["additional_entities"] = additional_entities
        r = httpx.post(self._url, json=body, timeout=self._timeout)
        r.raise_for_status()
        data = r.json()
        diag = data.get("diagnostics", {})
        return AuthorizationDecision(
            effect="allow" if data.get("decision") == "Allow" else "deny",
            determining_policies=diag.get("reason", []),
            diagnostics=diag.get("errors", []),
        )
