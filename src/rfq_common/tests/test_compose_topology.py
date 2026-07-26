"""Gateway-first topology (tmp/caddy-first-routing-analysis.md): the gateway
(Caddy in dev, GCP Apigee is the TARGET for test/prod) is the sole
externally-published ingress. Everything else is reachable only via the
gateway or the shared compose network's own internal DNS -- a host-published
port on any OTHER service is exactly the kind of accidental clash this
consolidation exists to prevent (e.g. a2a-inspector's first port choice,
8090, silently collided with an unrelated process on the dev host this
session). This test parses the real compose files directly, so a future
service that adds `ports:` without justification fails loudly here instead
of silently reintroducing that risk."""

from pathlib import Path

import yaml

RFQ_ROOT = Path(__file__).resolve().parents[3]

# Every service here is an explicitly justified developer-direct-access
# carve-out (admin console / seed script / debug access) -- not because
# peer services need them that way. Anything not listed must publish no
# host port at all.
JUSTIFIED_HOST_PORTS = {
    "gateway": {"443"},
    "keycloak": {"8081"},
    "vault": {"8200"},
    # a2a-inspector: gateway-routed (https://a2a-inspector.rfq-showcase.
    # localhost), not a host-port carve-out -- it's a peer dev surface, not
    # an admin console like Keycloak/Vault above.
}


def _load_services(compose_path: Path) -> dict:
    doc = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    return doc["services"]


def _published_host_ports(service: dict) -> set[str]:
    published = set()
    for entry in service.get("ports", []):
        # compose "ports:" entries are "HOST:CONTAINER" strings (or dicts under
        # the long form) -- only the host side is externally-published.
        if isinstance(entry, str):
            host_part = entry.split(":")[0]
            published.add(host_part)
        elif isinstance(entry, dict) and entry.get("published"):
            published.add(str(entry["published"]))
    return published


def test_support_stack_only_publishes_justified_host_ports():
    services = _load_services(RFQ_ROOT / "infra" / "compose.support.yaml")
    for name, service in services.items():
        published = _published_host_ports(service)
        expected = JUSTIFIED_HOST_PORTS.get(name, set())
        assert published == expected, (
            f"{name!r} publishes host ports {published!r}, expected exactly "
            f"{expected!r} -- unjustified host-port publish breaks the "
            f"gateway-first topology (every other service should be reachable "
            f"only via the gateway or compose-internal DNS)"
        )


def test_showcase_stack_publishes_no_host_ports_at_all():
    services = _load_services(RFQ_ROOT / "infra" / "compose.showcase.yaml")
    for name, service in services.items():
        published = _published_host_ports(service)
        assert not published, (
            f"{name!r} publishes host ports {published!r} -- showcase app "
            f"services must be reachable only via the gateway (external) or "
            f"compose DNS (internal peer traffic), never a host-published port"
        )


def test_showcase_network_is_external_and_shared_with_support():
    showcase = yaml.safe_load((RFQ_ROOT / "infra" / "compose.showcase.yaml").read_text(encoding="utf-8"))
    support = yaml.safe_load((RFQ_ROOT / "infra" / "compose.support.yaml").read_text(encoding="utf-8"))
    showcase_net = showcase["networks"]["rfq-showcase"]
    support_net = support["networks"]["rfq-showcase"]
    assert showcase_net.get("external") is True
    assert showcase_net["name"] == support_net["name"]
