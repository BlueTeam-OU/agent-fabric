---
role: "fabric-coordinator"
class: workflow
topic: "cross-host-share-via-control-plane"
description: "Agents may be on different hosts: whatever is shared travels through the control plane (fabric-ctl) or a git repository, never a host-local read (fabric-host run --as, another account's state, a scratchpad path)"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 50e819a6c88d9f39
---

## Agents may be on different hosts: whatever is shared travels through the control plane (fabric-ctl) or a git repository, never a host-local read (fabric-host run --as, another account's state, a scratchpad path)

The owner, 2026-10-10, while I planned memory upkeep: "remember, agents can be on
different host so everything is shared should be shared via control plane or git repo".
That morning I had counted every account's journal with `fabric-host develop-qzapp run --as
<login>`, and ADR-049's draft said its call log would be "read on the host" until an op
existed.

**Why:** placement is not identity (ADR-038); the fleet is spread over hosts
(`runtime/hosts/registry.json`), and a design that reads another account's files works
only while everyone happens to share one machine.

**How to apply:** when a design moves data between agents or to the coordinator, name its
carrier: a control-plane op (`fabric-ctl <login> …`, the per-account agent, ADR-029), the
harvest bundle, the GZCoord relay, or git. `fabric-host run` and the sudo backend are
break-glass for one host, never a design's path. A scratchpad or `/tmp` path is never
in a message to another agent. Related: [[delegate-to-subagents]].

*References: delegate-to-subagents*

*Observed 2026-10-10 (fabric-coordinator)*
