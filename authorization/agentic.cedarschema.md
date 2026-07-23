# agentic.cedarschema — GENERATED, not authored

**There is no hand-written `agentic.cedarschema` in this showcase, by design.**

In cpm-eaop the Cedar schema (`data/policies/agentic.cedarschema`, Cedar JSON) is
**generated**, never hand-edited — produced by `tools/generate_cedar_schema.py` from:

```text
ontology (taxonomy) + authz-projection.yaml + actions.yaml  ─►  agentic.cedarschema
```

Entity types + attributes + parents come from the **projection**; actions come
**verbatim** from the authored `actions.yaml` ("actions authored, never generated").
cedar-agent then **validates** all policies + data against the schema on `PUT`.

## For this standalone showcase

This is a design/decision package; the generator + sidecar live in cpm-eaop. When
the spike (`spikes/repricing/`) is built, generating the schema is the point where
the projection and the authored actions are validated together:

- every action in `business/actions.yaml` references only entity types declared in
  `authorization/authz-projection.yaml`;
- every context field is typed;
- `member_of` is the only parent relation.

Until then, the schema is intentionally absent — regenerating it from the two source
files is a spike step, not an artifact to copy by hand.

> Rule inherited from the runbook: **never edit the generated schema by hand.**
