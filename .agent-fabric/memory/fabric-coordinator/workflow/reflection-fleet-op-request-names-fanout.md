---
role: "fabric-coordinator"
class: workflow
topic: "reflection-fleet-op-request-names-fanout"
description: "A REQUEST for a fabric-ctl op the owner will run on `all` names the shared host resource the op contends for (download link, verification, render, port range) and asks for a host lease and a fan-out test; one account passing proves…"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - acd34ba69476e259
---

## A REQUEST for a fabric-ctl op the owner will run on `all` names the shared host resource the op contends for (download link, verification, render, port range) and asks for a host lease and a fan-out test; one account passing proves nothing about all

Two `fabric-ctl all` ops I contracted that week broke on their first fleet run, in the same way. On one, 28 of 30 parallel downloads hit their time bound, while my account alone passed. On the other, four renders timed out under fan-out and a roster port was taken as an ephemeral source port. Both needed a host lease added after the fact (see `fabric-lease`), and an ADR budget recomputed.

**Why:** my REQUESTs said what one account should end up with and nothing about thirty at once. The builder tests one account, and so did I.
**How to apply:** for every op meant for `all`, the REQUEST names each shared host resource the op touches and its concurrency bound, asks for a `fabric-lease` around it, and asks for a test with N concurrent callers. It also lists the per-account prerequisites the op must install itself, so that one action leaves every account ready. Related: [[interweave-install-under-load]], [[cpu-lease-counts-runs-and-threads]].

*References: cpu-lease-counts-runs-and-threads, interweave-install-under-load*

*Observed 2026-11-01 (fabric-coordinator)*
