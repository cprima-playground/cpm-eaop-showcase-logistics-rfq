# infra — provisioning + local infra stacks

Sibling to `../deploy`. Clean split:

- **`deploy/`** = the **plan** — GCP mapping, container strategy, phasing (*what/why*).
- **`infra/`** = the **artifacts** that provision and run it — IaC + local stacks
  (*how, runnable/provisioned*). Mirrors cpm-eaop `infra/`.

`TARGET` — sketches only in this pass; nothing is applied.

## Contents

```text
infra/
├── README.md
├── compose.sketch.yaml    # local whole-showcase topology (documentation)
├── caddy/                 # Caddyfile — local edge (*.localhost + local HTTPS)
├── cedar-agent/           # docker-compose for the Cedar PDP sidecar (reuse cpm-eaop)
├── vault/                 # ★ built — dev-only secrets store (ADR-009)
├── keycloak/              # ★ built — dev IdP (Dockerfile+compose) + keycloak/terraform/
│                          #   (realm/client/users, Terraform — mirrors cpm-eaop)
├── entra/                 # azuread Terraform (client-secret now → WIF target) — reuse infra/entra
├── dockerfiles/           # base.Dockerfile (rfq/base) + per-service Dockerfiles
├── terraform/             # GCP: Cloud Run services · Apigee · Artifact Registry ·
│                          #      Secret Manager · WIF · (Firestore if adopted)
└── cloudbuild/            # image builds per system + agent
```

## Boundary with `deploy/`

| Question | Home |
| --- | --- |
| Which GCP service hosts each component? | `deploy/README.md` |
| How are containers structured / warm instances / determinism? | `deploy/containers.md` |
| The actual Terraform / Dockerfiles / compose / Caddyfile / realm | **`infra/`** |

## Reuse from cpm-eaop

`infra/cedar-agent/docker-compose.yml` · `infra/keycloak` · `infra/caddy` ·
`infra/entra` · `infra/terraform` — copy the patterns; this showcase's `infra/`
follows the same layout so the two repos stay recognizable.
