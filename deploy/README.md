# Deploy — GCP mapping (plan)

`TARGET` — planning only, no IaC in this pass. How the showcase's mock systems,
agents, and control plane map onto GCP. Reuses the GEAP posture (Apigee front door,
internal observability) and the cpm-eaop control-plane spike (cedar-agent PDP, WIF
agent identity). IaC would be Terraform, mirroring cpm-eaop `infra/terraform` +
`infra/entra`.

## Principle

One GCP project (`rfq-showcase`). Every mock system is **one stateless container**
(in-memory store loaded from jsonl at boot) → **Cloud Run** service. Facets
(API / MCP / frontend / CLI) are separate Cloud Run services or containers over the
same image, never separate state.

## Component → GCP service

| Showcase component | GCP service | Notes |
| --- | --- | --- |
| Mock system backend+API (CRM/TMS/Rate/QMS/FX/Workflow) | **Cloud Run** (one service each) | jsonl fixtures baked into image; stateless |
| System frontends (QMS/CRM/Workflow full · TMS/Rate minimal) | **Cloud Run** — the chosen Jinja2+HTMX SSR frontend is served by the same FastAPI app (ADR-006) | per-system theme; static assets baked in or on Cloud Storage+CDN. A future SPA → Cloud Storage+CDN or Firebase Hosting |
| MCP servers (crm/tms/rate/commercial/approval) | **Cloud Run** | APIKEY from Secret Manager for server→backend |
| FX REST API | **Cloud Run** | machine service, APIKEY; no MCP |
| The 3 agents (lane/commercial/route) | **Vertex AI Agent Engine (ADK)** or **Cloud Run** | A2A between them |
| Cedar PDP (`cedar-agent`) + control-plane decision service | **Cloud Run** | private; only the control plane calls it |
| Front door / PEP | **Apigee** | VerifyJWT (Entra/Keycloak JWKS), quotas, routes to services — matches GEAP v1.7 PEP-1 |
| Human SSO IdP | **Keycloak** (Cloud Run/GKE) or **Google Identity Platform** / Entra | humans only |
| Agent identity | **Workload Identity Federation** | agents federate SA/OIDC → token; no stored secrets |
| Secrets (APIKEYs, client secrets) | **Secret Manager** | |
| Container images | **Artifact Registry** | |
| Observability (logs/traces/metrics/audit) | **Cloud Logging / Trace / Monitoring** | internal only, no external export |
| Networking | **VPC + Serverless VPC connector / PSC** | private southbound; Apigee at the edge |
| IaC | **Terraform** | mirror `infra/terraform` (GCP) + `infra/entra` (azuread) |

## Trust boundaries (map onto the v0.1 target)

```text
[ Agent runtime plane ]  Vertex AI Agent Engine / Cloud Run  — GOVERNED
        │ every invocation → PEP
[ Front door / PEP ]     Apigee (VerifyJWT · quotas)
        │ /authorize
[ Control plane ]        control-plane svc + cedar-agent (Cloud Run, PRIVATE)
        │ authorized dispatch
[ Systems plane ]        CRM/TMS/Rate/QMS/FX/Workflow (Cloud Run) — GOVERNED targets
[ Identity plane ]       Keycloak / Identity Platform (+ Entra), WIF for agents
[ Observability ]        Cloud Logging/Trace/Monitoring (internal)
```

## Planned files (when built)

```text
deploy/                       # the PLAN (what/why)
├── README.md                 ← this GCP mapping
├── containers.md             # container strategy (one image/component, local==GCP)
└── services.yaml             # component -> Cloud Run service name/region/env matrix

../infra/                     # the ARTIFACTS (how) — sibling folder
├── compose.sketch.yaml · caddy/ · cedar-agent/ · keycloak/ · entra/
└── dockerfiles/ · terraform/ · cloudbuild/
```

See **`containers.md`** for the container strategy; the runnable/provisioned
artifacts (Dockerfiles · compose · Caddyfile · Terraform · realm) live in **`../infra/`**.

## Open questions

1. ~~Agents on Vertex AI Agent Engine vs Cloud Run~~ — **decided: Vertex Agent Engine
   (ADK)** on GCP, local via the ADK runner in dev (ADR-008).
2. Persistence — **dev is zero-cost, all local**: in-memory (default) or **SQLite**
   (local file) for durability; **Firestore emulator** if you want the API for free.
   Real Firestore only for a *hosted* demo that must survive restarts (free tier is
   generous). Never in development.
3. SSO — **Keycloak** (matches cpm-eaop realm) vs **Identity Platform** for the
   showcase humans; Entra as a second IdP via the claim contract.
4. One Apigee env for the showcase, or API Gateway for a lighter footprint?
5. ~~Where the second authorization boundary (tool→API) is enforced~~ — **out of
   scope** for the showcase (ADR-008 Related): only agent→tool is governed here.
