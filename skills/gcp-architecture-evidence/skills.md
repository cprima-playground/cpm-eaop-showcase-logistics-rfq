# Skill: extract GCP architecture evidence from this reference implementation

How to reverse-engineer exactly which GCP capabilities, APIs, IAM
permissions, and identity mechanisms this repository's implementation
actually depends on — evidence for `building-blocks.yaml`, not a target
architecture design exercise.

## Background: why evidence, not assumption

This repository is a **reference implementation** running in a personal
Google Cloud project with broad/full permissions. The target corporate
environment is heavily permission-constrained. Successful execution here
does **not** prove the same implementation is available or permitted
corporately.

The method is:

**Reference implementation → evidence → building blocks → capabilities**

Do not design the target architecture. Reverse-engineer the GCP
dependencies this implementation demonstrates, and flag what still needs
corporate verification.

## What to search for

Search the entire repository — source code, Terraform/IaC, shell scripts,
CI/CD, Dockerfiles, manifests, configuration, environment variables, tests,
examples, documentation.

### GCP SDKs and APIs

Search imports and dependencies:

```text
google.cloud
google.auth
google.oauth2
google.api_core
googleapiclient
google-cloud-*
google-auth
google-auth-library
gcloud
```

Identify every Google Cloud client instantiated and every API called, e.g.
`google.cloud.storage`, `google.cloud.aiplatform`, `google.cloud.run`,
`google.cloud.secretmanager`, `google.cloud.pubsub`. Also check for direct
REST calls to `*.googleapis.com` (`iam`, `iamcredentials`, `sts`, `oauth2`,
`aiplatform`, `run`, `secretmanager`, `logging`).

Record the actual *operation*, not merely the service — "Secret Manager is
imported" is weaker evidence than "`secretmanager.versions.access` is
required at runtime."

### Identity and authentication

Look for: Application Default Credentials, `google.auth.default()`, service
accounts, `GOOGLE_APPLICATION_CREDENTIALS`, access/ID tokens, OIDC/OAuth/JWT,
STS, Workload Identity (Federation), service-account impersonation,
`generateAccessToken`/`generateIdToken`/`signBlob`, `iamcredentials`,
`audience`, `principal`/`principalSet`.

Determine, per workload: what identity executes it; how credentials are
obtained; whether user ADC is used during development; whether
impersonation occurs; token audiences where visible; whether workload
identity/federation is actually implemented or merely discussed. Do not
infer corporate identity behavior from personal-project ADC.

### IAM and authorization

Search for `roles/`, `setIamPolicy`/`getIamPolicy`/`testIamPermissions`,
`serviceAccount*`, `workloadIdentityUser`, `principal`/`principalSet`,
`member`/`bindings`/`policy`; in Terraform/IaC especially
`google_project_iam_*`, `google_service_account_iam_*`, `google_*_iam_*`.

Capture `principal → role → resource` wherever the repository provides
enough evidence. Record exact predefined role IDs, or exact permissions for
custom roles. Flag broad roles (`roles/owner`, `roles/editor`,
`roles/iam.serviceAccountAdmin`, `roles/resourcemanager.projectIamAdmin`) —
they may be hiding the real minimum-permission dependency.

### Google Cloud resource creation

Search Terraform/Pulumi/Deployment Manager/`gcloud`/scripts/application code
for `resource "google_`, `data "google_`, `gcloud ... create/deploy`. For
every resource: type, creation mechanism, runtime dependency, configuration
dependency, IAM dependency.

**Distinguish provisioning-time from runtime permissions** — this matters:
provisioning (create Cloud Run service, attach service account, configure
IAM) and runtime (invoke Cloud Run service, access Secret Manager secret,
publish Pub/Sub message) are different corporate permission requirements.

### APIs and service enablement

Search `google_project_service`, `serviceusage`, `services enable`,
`gcloud services enable`, `*.googleapis.com`. Produce the set of GCP APIs
the implementation assumes are enabled. Do not assume an API is available
corporately because it is available in the personal project.

### Vertex AI / Gemini / agent-specific dependencies

Search for Vertex AI, `vertexai`/`aiplatform`, Gemini, `GenerativeModel`,
`google.genai`, Agent Engine, Reasoning Engine, ADK/`google.adk`, MCP/Model
Context Protocol, tool/function calling, grounding. For each finding:
concrete API, resource, region, model, authentication mechanism, runtime
identity, required permissions where evidenced. Distinguish Google-managed
agent functionality from custom code implementing equivalent behavior.

### Cloud Run and workload execution

Search Cloud Run, `run.googleapis.com`, `google_cloud_run(_v2)`,
`gcloud run`, `run.app`, `K_SERVICE`/`K_REVISION`/`PORT`. Determine: what
runs on Cloud Run, service identity, invocation model, authenticated vs.
unauthenticated invocation, service-to-service auth, ID-token audience,
ingress config, region, environment/secrets. If one workload calls another,
trace the authentication path end to end.

### Secret Manager and KMS

Search Secret Manager/`secretmanager`, secret versions, KMS/`cloudkms`,
encrypt/decrypt. Identify which components need secret access vs. secret
*administration* vs. encryption/decryption vs. key administration — do not
collapse runtime secret access and administrative secret management into
one requirement.

### Networking

Search VPC, subnet, serverless VPC access/connector, Private Google Access,
Private Service Connect, NAT, ingress/egress, firewall, load balancer,
internal/external, DNS. Identify whether the implementation implicitly
depends on unrestricted public networking in the personal project, and flag
any external endpoint the workload calls — corporate network restrictions
may invalidate an otherwise available GCP component.

### Artifact Registry, build and deployment

Search Artifact Registry, Cloud Build, Docker, `gcloud builds`/
`gcloud run deploy`, GitHub Actions, Workload Identity Federation, service
account keys. Separate build identity, deployment identity, and runtime
identity — record permissions/resources required by each.

### Storage, messaging and state

Search Cloud Storage/GCS, Pub/Sub, Firestore, BigQuery, Spanner, Cloud SQL,
Redis/Memorystore, Cloud Tasks, Scheduler, Eventarc. For each: required
runtime infrastructure vs. optional vs. development-only vs. test fixture.
Capture concrete operations (read/write/publish/subscribe/query/create/
delete/administer) where visible.

## Permission analysis

The personal project has broad permissions. Do not report "the
implementation works on GCP" — report "the implementation works when the
following GCP operations are permitted," using three categories:

- **PROVISIONING** — resources/APIs/IAM needed to establish the environment.
- **DEPLOYMENT** — permissions needed to deploy/update workloads.
- **RUNTIME** — permissions needed by the running workload.

Do not invent exact IAM permission names the code does not establish. If
exact mapping requires external GCP documentation, report
`NEEDS GCP VERIFICATION` and state the observed API operation/resource that
needs verification.

## Required output

1. **GCP dependency inventory** — table of `GCP service/resource | Used by
   | Operation | Phase | Evidence`, only entries backed by repository
   evidence.
2. **Identity and permission paths** — per important path:
   `Actor/workload → authenticates as → GCP principal → invokes/accesses →
   GCP resource/API → operation → observed operation`. Mark unknowns
   explicitly.
3. **Personal-project assumptions** — anything that may work only because
   the reference project is permissive: broad IAM roles, user ADC, ad hoc
   resource creation, API enablement, impersonation, public ingress/egress,
   cross-service invocation, secret access, IAM policy mutation,
   project-level access. High-value findings.
4. **Evidence-backed building blocks** — only after the GCP analysis above,
   map findings onto existing `building-blocks.yaml` entries: `Building
   block / GCP realization / Evidence / Required GCP capability /
   Permission-availability dependency`. Do not invent new building blocks
   merely because a GCP product exists.
5. **Corporate availability questions** — a checklist of facts that must be
   verified in the constrained corporate environment (e.g. "Is
   `iamcredentials.googleapis.com` enabled?", "Can workload service
   accounts generate ID tokens?"), each phrased so it can later be answered
   `AVAILABLE` / `RESTRICTED` / `NOT AVAILABLE` / `UNKNOWN`.
6. **Gaps**, evidence-based only:
   - **Implementation gap** — building block expected but not demonstrated.
   - **Permission gap** — implementation requires an operation not known to
     be permitted corporately.
   - **Availability gap** — required GCP service/component not known to be
     available corporately.
   - **Evidence gap** — repository doesn't establish enough information to
     make the architectural claim.

## Don't

- Don't infer corporate identity/permission/availability behavior from what
  works in this permissive personal project — every claim needs its own
  evidence trail back to the repository, not an assumption from success
  here.
- Don't invent exact IAM permission names, or new `building-blocks.yaml`
  entries, that the repository's evidence doesn't establish — use
  `NEEDS GCP VERIFICATION` instead of guessing.
- Don't turn `UNKNOWN` into `NOT AVAILABLE` — those are different claims
  requiring different evidence.
- Don't collapse provisioning-time and runtime permissions, or runtime
  secret access and administrative secret management, into one requirement
  — corporate environments frequently permit one and not the other.

## Grounding rule

Every architectural conclusion must have a path back to concrete repository
evidence. The purpose is not to describe what GCP *can* do — it's to
establish exactly what this reference implementation **demonstrates that it
needs** from GCP, so those dependencies can be compared against the
corporate platform later.

**Reference implementation → GCP evidence → building blocks →
capabilities.**
