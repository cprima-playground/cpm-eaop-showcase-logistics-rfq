"""ObservedServiceRegistry -- M8.2. Named deliberately: this OBSERVES
(polls each service's own real GET /descriptor, D1) -- it does not
REGISTER, admit, evict, or own service lifecycle. A future, distinct
milestone might introduce an AuthoritativeRuntimeRegistry
(REGISTER/HEARTBEAT/DEREGISTER-backed); this is not that, and must never
be confused for it, in code or in what it claims about a service's
liveness.

Standing invariant (binds every future registry milestone too, not just
this one): loss of Mission Control or this registry must never interrupt
established data-plane communication. Agents/MCP servers resolve a peer's
endpoint via rfq_common.service_resolver, once (or cached) -- never a
synchronous call to Mission Control per A2A/MCP invocation. Mission
Control enables discovery and governance; it does not sit in the request
path.

Roster derivation, mechanical, not hand-maintained:
  agents/catalog.yaml (excluding `fixture: true` entries, e.g.
      trust-boundary-fixture-agent -- a real Cedar test fixture, never a
      registry entry)
  + interfaces/mcp/tools.yaml
  -> 3 agent canonical ids + 4 MCP-server canonical ids = 7 total.

mock-* business systems are deliberately NEVER registry entries (no
`/descriptor` exists on any of them) -- they appear only as dependency
targets in /api/v1/topology and as probe targets in /api/v1/health's
BROADER, separate roster (rfq_common/probe.py, M8.3) -- registry
membership and health-probe membership are two different questions
answered by two different rosters (see api.py's module docstring)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import httpx
import yaml

from rfq_common.service_resolver import EnvironmentServiceResolver

RFQ_ROOT = Path(__file__).resolve().parents[3]

# canonical_id -> env var carrying that service's real base URL. Every
# entry here is a NEW env var this service alone consumes (M8.1's compose
# wiring) -- no other service in this repo needs to resolve every peer,
# by ADR-002's own "no agent gets a registry of every other service"
# rule; Mission Control is the one place that legitimately does.
_ENDPOINT_ENV_BY_CANONICAL_ID = {
    "agent.lane-evaluation": "LANE_EVALUATION_AGENT_URL",
    "agent.route-decision": "ROUTE_DECISION_AGENT_URL",
    "agent.commercial-normalization": "COMMERCIAL_NORMALIZATION_AGENT_URL",
    "workload.tms-mcp": "TMS_MCP_URL",
    "workload.rate-mcp": "RATE_MCP_URL",
    "workload.qms-mcp": "QMS_MCP_URL",
    "workload.approval-mcp": "APPROVAL_MCP_URL",
}

DEFAULT_TTL_SECONDS = 15.0


def _resolver() -> EnvironmentServiceResolver:
    return EnvironmentServiceResolver(dict(_ENDPOINT_ENV_BY_CANONICAL_ID))


def registry_roster(root: Path | None = None) -> list[str]:
    """The canonical ids ObservedServiceRegistry polls -- 3 real agents
    (fixture excluded) + 4 real MCP servers, derived from the same files
    every other identity/capability consumer in this repo reads, never a
    separately maintained list."""
    root = root or RFQ_ROOT
    catalog = yaml.safe_load((root / "agents" / "catalog.yaml").read_text(encoding="utf-8"))
    agent_ids = [
        "agent." + a["id"].removesuffix("-agent")
        for a in catalog["agents"]
        if not a.get("fixture", False)
    ]
    tools = yaml.safe_load((root / "interfaces" / "mcp" / "tools.yaml").read_text(encoding="utf-8"))
    workload_ids = ["workload." + s["id"] for s in tools["servers"]]
    return agent_ids + workload_ids


@dataclass
class RegistryEntry:
    canonical_id: str
    reachability: Literal["reachable", "unreachable"]
    observed_at: float
    last_seen: float | None  # None if NEVER successfully observed
    descriptor: dict | None  # None while unreachable and never seen


@dataclass
class ObservedServiceRegistry:
    """Lazy TTL cache over live GET /descriptor polls. Single-flight per
    refresh call -- concurrent requests within the TTL window reuse the
    same cached snapshot, never fan out N parallel poll rounds."""

    root: Path = field(default_factory=lambda: RFQ_ROOT)
    ttl_seconds: float = DEFAULT_TTL_SECONDS
    timeout_seconds: float = 5.0
    client: httpx.Client | None = None

    def __post_init__(self) -> None:
        self._client = self.client or httpx.Client(timeout=self.timeout_seconds)
        self._resolver = _resolver()
        self._entries: dict[str, RegistryEntry] = {}
        self._last_refresh: float = 0.0
        self._refresh_lock = threading.Lock()

    def _poll_one(self, canonical_id: str, now: float) -> RegistryEntry:
        prior = self._entries.get(canonical_id)
        try:
            endpoint = self._resolver.resolve(canonical_id)
            resp = self._client.get(f"{endpoint}/descriptor")
            resp.raise_for_status()
            descriptor = resp.json()
            return RegistryEntry(
                canonical_id=canonical_id, reachability="reachable",
                observed_at=now, last_seen=now, descriptor=descriptor,
            )
        except Exception:
            # A degraded peer must never fail the registry response --
            # it stays present, marked unreachable, with whatever it was
            # last seen as (or None if never successfully observed).
            return RegistryEntry(
                canonical_id=canonical_id, reachability="unreachable",
                observed_at=now, last_seen=prior.last_seen if prior else None,
                descriptor=prior.descriptor if prior else None,
            )

    def refresh(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (now - self._last_refresh) < self.ttl_seconds and self._entries:
            return
        with self._refresh_lock:
            # Re-check under the lock -- a concurrent caller may have
            # already refreshed while this one was waiting (real
            # single-flight, not just a docstring claim).
            now = time.monotonic()
            if not force and (now - self._last_refresh) < self.ttl_seconds and self._entries:
                return
            for canonical_id in registry_roster(self.root):
                self._entries[canonical_id] = self._poll_one(canonical_id, now)
            self._last_refresh = now

    def list_entries(self) -> list[RegistryEntry]:
        self.refresh()
        return [self._entries[cid] for cid in registry_roster(self.root)]

    def get_entry(self, canonical_id: str) -> RegistryEntry | None:
        self.refresh()
        return self._entries.get(canonical_id)

    def resolve_endpoint(self, canonical_id: str) -> str:
        """Intentional seam for other read models (health.py) that need
        this registry's endpoint resolution without reaching into
        private state (_resolver)."""
        return self._resolver.resolve(canonical_id)
