---
role: "fabric-coordinator"
class: rationale
topic: "h2-agents-live-first"
description: "owner 2026-11-14: no build/test offload to fabric-h2; move when agents can live there on InterWeave (data + control); cutover path is top priority"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a2cb46da0526510d
---

## owner 2026-11-14: no build/test offload to fabric-h2; move when agents can live there on InterWeave (data + control); cutover path is top priority

The owner said this in the coordinator's session on 2026-11-14. I had proposed a stage 1 that used fabric-h2 as a build and test executor over SSH while agents stayed on develop-qzapp. The owner answered: "no. we will move when we can put agents live there ... so we have to priorityze these jobs".

So there is no compute offload to h2. The goal is agents living on fabric-h2, with GZCoord data and fabric:control both over InterWeave. Everything on that path goes ahead of other work.

Measured the same day: VM 101 has 2 vCPU, 7 GB RAM and 30 GB /home, at load 0. develop-qzapp has 10 CPU at load 21-34. The VM needs resizing before agents can live there, and that question is still open with the owner.

How I applied it on 2026-11-14:
- The open cutover waves had no owner, so I dispatched them:
  - W6, W7, W8 to python-dev-04 (REQUEST 01a1da1a-4e05), after its j123.
  - W13 and W9 to python-dev-01 (REQUEST 01a1da1a-59f2), after its j242.
- python-dev-03's j144 is the agentd Broken pipe issue (my j872).
- I set my own jobs to blocking: j871 (operator's own row), j798, j794 (W2 drills), j849 (scratch-login read-back), j879 (W1 remainder) and j880 (fabric-h2 two-host read-back).
- W11 still waits on D6.

Related: [[edge-hosting-h2-waits-on-control-plane]], [[d9-public-port-fabric-h2]], [[h2-owner-answers-2026-11-11]], [[interweave-only-cutover-owner-decisions]].

*References: d9-public-port-fabric-h2, edge-hosting-h2-waits-on-control-plane, h2-owner-answers-2026-11-11, interweave-only-cutover-owner-decisions*

*Observed 2026-11-14 (fabric-coordinator)*
