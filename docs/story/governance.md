# Governed autonomy

Autonomy is not the absence of controls. It is the ability to complete bounded
work without a person directing every intermediate step, while still proving
who acted, what they attempted, and why the action was allowed.

## The control path

- **AuthN** identifies the human, agent, or service workload.
- The **PEP** is the enforcement gateway in the control panel. It intercepts
  the requested business action before the action reaches a tool or system.
- The **PDP** evaluates identity, action, resource, and business context against
  policy.
- The **policy result** is allow, deny, or allow with an obligation.
- The **obligation** may require a human approval, notification, or another
  recorded consequence.

The PEP is important because a policy decision that is not enforced is only a
recommendation. The showcase makes the control-panel PEP part of the execution
path, including agent-to-agent delegation and agent-to-MCP access.

## Separation of duties

The agents can evaluate, normalize, compare, and recommend. They cannot approve
their own commercial exceptions. A human approval is represented as a durable
business-state transition in the quotation system, which makes it visible,
auditable, and resumable.

This keeps the message practical: the showcase automates selected work around a
decision, while preserving human accountability for the decision itself.

## Why policy belongs outside the agent

If each agent embedded its own authorization logic, the organization would have
to inspect and update many independent implementations. A shared policy decision
and enforcement path gives the enterprise one place to express boundaries such
as:

- this agent may read capacity but may not approve a deviation;
- this action is allowed only for a quote in a particular state;
- this variance requires human review;
- this delegation may proceed only within a bounded chain.

The agent remains useful and adaptive. The business boundary remains explicit.
