---
role: "domain-transit"
class: workflow
topic: "fabric-tools-run-from-checkout"
description: "before running a fabric tool a request names \"on main\", fast-forward the agent-fabric checkout — the fabric-* commands on PATH run whatever it holds"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "domain-transit"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f0730c48f3186eb9
---

## before running a fabric tool a request names "on main", fast-forward the agent-fabric checkout — the fabric-* commands on PATH run whatever it holds

The fabric commands on PATH (`gzcoord-carrier`, the `fabric-*` tools) are symlinks
into the login's own agent-fabric checkout's `bin/`, so the code that runs is
whatever that checkout holds, not origin/main. On 2026-10-25 (j19, ADR-064 roster
row, REQUEST 01a174b1-ea9a-72a7-a1e4-7d5d09761827) the checkout was 11 commits
behind; `git fetch && git merge --ff-only origin/main` first, then
`gzcoord-carrier roster-row` printed the row (exit 0; public peer id + PGP
signature, no secret), sent in REPLY 01a174b2-b82a-75d7-b2d3-21efc798323a.

**Why:** a request saying "from your checkout on main" assumes current tooling;
a stale checkout runs old code silently.
**How to apply:** fetch and fast-forward the agent-fabric checkout before any
fabric tool a request asks to run; the checkout is read-only for commits, never
for pulls.

*Observed 2026-11-03 (domain-transit)*
