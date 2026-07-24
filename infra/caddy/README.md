# Caddy (dev) — local edge, real local HTTPS

Fronts the ops-dashboard and Keycloak under stable `*.rfq-showcase.localhost`
names instead of bare ports. Namespaced (not a bare `*.localhost`) to avoid
colliding with any other project's generically-named local services.

**Real HTTPS is required, not optional**: Keycloak marks its session cookies
`Secure`, which get silently dropped over plain HTTP for any hostname other
than literally `localhost` — see `KNOWN-ISSUES.md`. Caddy issues certs from
its own internal CA (not public ACME — these aren't real domains).

## Run it

```sh
docker compose up -d --build      # rfq-showcase-caddy on :443 (standard HTTPS --
                                    # cpm-eaop's own Caddy only holds :80, verified free)
```

### One-time: hosts-file entries

Windows' hosts file has no wildcard support, so each subdomain needs its own
literal line. **Requires an elevated shell.** Thinking ahead to every planned
frontend (`systems/mock-architecture.md`'s capability matrix — QMS/CRM/Workflow
all get one eventually; TMS/Rate/FX/Masterdata never do, machine-only APIKEY):

```powershell
Add-Content -Path "$env:WINDIR\System32\drivers\etc\hosts" -Value "`n127.0.0.1 keycloak.rfq-showcase.localhost`n127.0.0.1 ops-dashboard.rfq-showcase.localhost`n127.0.0.1 qms.rfq-showcase.localhost`n127.0.0.1 crm.rfq-showcase.localhost`n127.0.0.1 workflow.rfq-showcase.localhost"
```

Why this is needed at all (not just cosmetic): `curl`/browsers already
special-case any `*.localhost` name as loopback per RFC 6761, with **zero**
hosts-file entries. Python's `socket.getaddrinfo` (what `httpx`/uvicorn use)
does **not** honor that convention on this Windows box — confirmed directly;
`ops_dashboard/sso.py`'s own server-side token-exchange call to Keycloak would
fail to resolve the hostname without these entries, breaking the real
`/callback` flow, not just manual curl testing.

### One-time: trust Caddy's internal CA

Extract the CA root cert (regenerates if the `caddy-data` volume is ever
removed — re-extract after that):

```sh
docker cp rfq-showcase-caddy:/data/caddy/pki/authorities/local/root.crt ./root.crt
```

Then trust it system-wide (elevated shell; this is what makes the browser
accept the cert without a warning):

```powershell
Import-Certificate -FilePath .\root.crt -CertStoreLocation Cert:\LocalMachine\Root
```

`ops_dashboard/config.py::caddy_ca_bundle()` also points our own backend's
httpx calls (token exchange, JWKS fetch) at this same file directly — so the
backend doesn't depend on the OS trust store at all, only the browser does.

## What's fronted

| Hostname | Proxies to |
| --- | --- |
| `ops-dashboard.rfq-showcase.localhost` | `host.docker.internal:8006` (the dashboard app) |
| `keycloak.rfq-showcase.localhost` | `host.docker.internal:8081` (dev Keycloak) |

`host.docker.internal` is Docker Desktop's route from a container back to
processes running on the host (both the dashboard and Keycloak run as
regular `uv run .../docker compose` processes, not inside this Caddy's own
network).
