# Terraform — cpm-geap-2026 spike resources

Scope: only the two GCP resources this repo's own spikes created
(`spikes/hello-agent-adk`, `spikes/hello-mcp`), in project `cpm-geap-2026`.
Deliberately does not touch or import anything `cpm-eaop` already manages
(its own separate `infra/terraform/`, separate state) — different repo,
out of scope here.

- `hello-agent-adk.tf` — `google_vertex_ai_reasoning_engine.hello_agent_adk`
  (`reasoningEngines/504070555998093312`). Requires provider `~> 7.42` — this
  resource type doesn't exist in older `google` provider versions (checked:
  absent through 6.50.0, present and documented as of 7.x).
- `hello-mcp.tf` — `google_cloud_run_v2_service.hello_mcp` +
  `google_cloud_run_v2_service_iam_member.hello_mcp_public` (the
  `--allow-unauthenticated` binding).

Both resources were originally deployed outside Terraform (raw
`vertexai.agent_engines.create()` / `gcloud run deploy --source`) and
**imported** into this state afterward via
`terraform plan -generate-config-out` + `terraform import` blocks — the
`.tf` content reflects what was actually live, not a hand-authored spec.
`terraform plan` shows zero drift as of the import date.

```sh
terraform init
terraform plan   # should show "No changes" unless something drifted
```
