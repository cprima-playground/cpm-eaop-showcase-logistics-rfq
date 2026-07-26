# Logistics agentic showcase — exposition

This folder explains the showcase for business, product, architecture, and
operations audiences. It deliberately starts with logistics rather than with
agent protocols.

## The storyline

**Logistics business → jobs → responsibilities → agents → A2A → MCP → existing
APIs → systems of record → AuthN → PEP/PDP → policies → governed autonomy**

The central message is:

> The systems of record remain; selected human responsibilities become agent
> capabilities, A2A connects those capabilities, MCP connects them to enterprise
> systems, and PEP/PDP keeps every business action governed.

## Contents

- [The exposition](exposition.md) — the complete non-technical narrative.
- [Logistics roles and agent responsibilities](roles.md) — generated from the
  canonical organization and job-title data.
- [The agent architecture](architecture.md) — A2A, MCP, APIs, and systems of
  record in plain language.
- [Governed autonomy](governance.md) — identity, authorization, policy, and the
  control-panel PEP.
- [LinkedIn release draft](linkedin-release.md) — a public announcement draft.

The machine-readable job/workload projection is generated at
`data/story/workload-to-jobs.yaml`. It combines the job-responsibility bridge
with the implemented agents, MCP servers, system APIs, directory hierarchy,
and policy-relevant groups.

## Regenerating the role chapter

The role chapter is derived from:

- `business/departments.yaml`
- `business/job-titles.yaml`
- `agents/catalog.yaml`

Run:

```text
uv run --project src/rfq_common python tools/story/generate_roles.py
```

The generated file is `docs/story/roles.md`. The explanatory mapping of
responsibilities to agent capabilities is intentionally small and explicit in
the generator: it is a teaching aid, not a claim that an entire job has been
automated.
