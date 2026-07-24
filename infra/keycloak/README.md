# Keycloak (dev) — local human SSO for the ops-dashboard

Dev-only IdP. Test/prod use Entra (`deploy/environments.md`). Backs the
ops-dashboard's first-ever human login in RfQ (`src/ops-dashboard/`,
`identity/claims-contract.md`).

## Run it

```sh
docker compose up -d --build                  # rfq-showcase-keycloak on :8081
                                                # (:8080 is used by cpm-eaop's own Keycloak)
cd terraform
terraform init
terraform apply                                # realm `rfq`, ops-dashboard-web
                                                # client, alice (ops-viewer)/bob (no role)
terraform output -raw ops_dashboard_web_client_secret
```

Fixed dev admin (`admin`/`rfq-dev-admin`) and shared test-user password
(`rfq-dev-user`) — same posture as `infra/vault`'s fixed dev root token.
**Never use dev mode outside dev.**

## What's provisioned

- Realm `rfq`.
- `ops-dashboard-web` — Authorization Code + PKCE client (confidential),
  redirect `https://ops-dashboard.rfq-showcase.localhost/callback` (via
  `infra/caddy`, the real path -- see its README for the required hosts-file
  entries + CA trust step) and `http://localhost:8006/callback` (direct,
  bypasses Caddy/Keycloak's Secure-cookie requirement since bare `localhost`
  is an implicit secure context). Claim mappers shape the token to
  resemble Entra (`tid`, `oid`, `groups`, `roles`) so `rfq_common.identity`'s
  claims-contract normalization doesn't change when Entra replaces Keycloak.
  Also has `direct_access_grants_enabled = true` (ROPC/password grant) —
  **test-only deviation** from a real client, used solely by the skip-gated
  live-integration test to mint a token without driving a browser through
  the PKCE redirect.
- Role `ops-viewer`, group `Ops`.
- `alice` (has `ops-viewer` — sees the dashboard), `bob` (logged in, no role —
  proves the 403 role-gate path).

Not the full enterprise `identity/groups.yaml` buildout (a separate, larger
TODO item) — just enough to prove role-gating end to end.
