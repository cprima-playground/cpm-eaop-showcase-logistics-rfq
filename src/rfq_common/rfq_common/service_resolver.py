"""M5.5: ServiceResolver abstraction (tmp/RuntimeConfigurationContract
ServiceRegistryFoundation.md #6) -- added now, cheap, so extracting
hardcoded `*_URL` reads out of every A2A executor's business logic after
M6 triples the service count doesn't have to happen later.

`endpoint = resolver.resolve("agent.lane-evaluation")` -- the calling
code (an executor building an A2ACardResolver, or an MCP client building
its downstream httpx.AsyncClient) never knows or cares whether the
endpoint came from an env var, DNS, Kubernetes, Consul, or a future
service registry.

Today: EnvironmentServiceResolver only -- wraps the SAME `*_AGENT_URL`/
`*_MCP_URL`/`*_API_URL` env var reads every service already does,
unchanged behavior, just behind one interface. A RegistryServiceResolver
is explicitly future/deferred scope (M5.5 does not build a registry) --
when one exists, it becomes an alternative resolver behind this same
ServiceResolver interface, not a replacement for explicit env-var
topology.

Deliberately does NOT get pulled into authorization: resolving an
endpoint says nothing about whether the caller may use it -- that
remains Cedar's job (agent.delegate/can_call for A2A, the mapped
business action for MCP), entirely independent of this module.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod


class ServiceResolutionError(KeyError):
    pass


class ServiceResolver(ABC):
    @abstractmethod
    def resolve(self, canonical_id: str) -> str:
        """Returns the base URL for `canonical_id` (e.g. "agent.lane-
        evaluation", "workload.tms-mcp"). Raises ServiceResolutionError
        if this resolver has no answer for that identity."""
        raise NotImplementedError


class EnvironmentServiceResolver(ServiceResolver):
    """`mapping`: canonical_id -> env var name. Only the dependencies a
    process ACTUALLY calls should be in its mapping -- per the plan, no
    agent gets a registry of every other service; agents/catalog.yaml is
    the capability model, this mapping is deployment topology, and the
    two stay separate on purpose."""

    def __init__(self, mapping: dict[str, str]):
        self._mapping = mapping

    def resolve(self, canonical_id: str) -> str:
        env_name = self._mapping.get(canonical_id)
        if not env_name:
            raise ServiceResolutionError(
                f"no configured dependency for {canonical_id!r} (known: {sorted(self._mapping)})"
            )
        value = os.environ.get(env_name)
        if not value:
            raise ServiceResolutionError(f"{env_name} is not set (resolving {canonical_id!r})")
        return value
