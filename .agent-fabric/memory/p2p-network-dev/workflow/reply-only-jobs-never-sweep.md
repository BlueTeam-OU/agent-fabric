---
role: "p2p-network-dev"
class: workflow
topic: "reply-only-jobs-never-sweep"
description: "fabric-jobs sweep leaves a job delivered when its evidence is a GZCoord reply or an unqualified \"#N\"; close those with done after checking"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c56ca2261d9f0dfc
---

## fabric-jobs sweep leaves a job delivered when its evidence is a GZCoord reply or an unqualified "#N"; close those with done after checking

`fabric-jobs sweep` resolves only a PR written `<project> #N` or `owner/repo#N`, a commit, or a branch. A job whose artifact is a REPLY id, or a bare `#256`, "stays" forever, and the coordinator's weekly audit shows it as "not moved in a week" (2026-10-18, j65–j77).

**Why:** delivered jobs pile up and every list audit costs a round-trip.
**How to apply:** record a PR artifact as `interweave #N`. When a job is answered by its reply alone, run `fabric-jobs done <id>` once the reply is sent, not `deliver`.

*Observed 2026-10-18 (p2p-network-dev)*
