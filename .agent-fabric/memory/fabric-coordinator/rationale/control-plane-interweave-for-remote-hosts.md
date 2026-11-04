---
role: "fabric-coordinator"
class: rationale
topic: "control-plane-interweave-for-remote-hosts"
description: "owner 2026-10-27: the control plane moves onto InterWeave, driven through the InterWeave CLI, so agents can be moved to remote hosts; design cross-host first (j422)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 186352d02ccef592
---

## owner 2026-10-27: the control plane moves onto InterWeave, driven through the InterWeave CLI, so agents can be moved to remote hosts; design cross-host first (j422)

The owner's direction, 2026-10-27: fabric:control (ADR-029) moves onto InterWeave. Each control agent drives the InterWeave CLI (`interweave-human` send and listen with --json) as its carrier, not a library binding and not a second bridge. The aim is to move agents to remote hosts. The relay and the per-account control plane assume one host today, and ADR-064 rule 1 keeps InterWeave to one host over loopback. That is why the owner keeps pressing for the CLI to be ready. Job j422 drafts the design and the ADR-029/064/033 amendments.

**Why:** when the owner asked "does the control plane use InterWeave?", I answered about rule 12 and missed the goal behind the question. A remote agent needs both planes across hosts.

**How to apply:** when the owner raises InterWeave readiness, the CLI or moving an agent, read it as the cross-host goal. Weigh any InterWeave or control-plane change by whether it moves a first remote agent closer. Ask the owner which host before building. Related: [[cross-host-share-via-control-plane]], [[gzcoord-not-on-interweave]].

**State 2026-10-28:** the design lives at docs/proposals/j422-control-plane-on-interweave-cli.md. It is on PR #417 with ADR-029 rule 18, ADR-064 rule 12 and ADR-033 §7 (the on-host part only). The CLI gaps G1-G4 and G6, plus R9 (`--consume` drains at open), shipped in InterWeave v0.2.0 (#477). X2's one-profile case is on InterWeave main. G7 and G8 are routed (architect-cto REPLY 01a181d9). The owner's word on the 5b limits is InterWeave #500. The second-host amendment waits for Q1-Q5 and Q7 (H2 is unnamed). Open fabric gaps: F1 (interweave-human in the pin's reports) and F3 (bin/fabric-op). During the dual run, an account splits a reply once at the InterWeave bound for both carriers, and the PeerId-authenticated copy is the row (#417 F1, F2).

*References: cross-host-share-via-control-plane, gzcoord-not-on-interweave*

*Observed 2026-10-27 (fabric-coordinator)*
