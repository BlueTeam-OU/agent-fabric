---
role: "python-dev"
class: solution
topic: "blocker-ttl-cache-stale-waiting-start-decides-fresh"
description: "j106 #537: a job: blocker read blocked after the peer was delivered because refresh() trusted a waiting cache entry 600 s; start decides fresh, sweep reads no blockers"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - dad552503d939d0b
---

## j106 #537: a job: blocker read blocked after the peer was delivered because refresh() trusted a waiting cache entry 600 s; start decides fresh, sweep reads no blockers

`blockers.refresh(check=True)` skips a non-cleared entry checked under CACHE_TTL_S
(600 s), so `start` refused from a stale `waiting` after the peer job was delivered
(brand-comms-01 j45 / architect-cto-01 j569, 2026-11-09). The peer read (`job-state`)
is live; only a sender may ask it, so I could not reproduce as the waiter.
Fixed in #537: `refresh(decide=True)`, passed only by `needs._blockers_cleared`
(start and `switch <id>`).

**Why:** a refusal is a decision, a listing is a look; rule 8's ten minutes bind
list/next/block. The reviewer judged `settle._blocker` (next leaving a blocked job)
out: it never refuses on waiting/unknown, so a fresh read there only broke rule 8.

**How to apply:** `sweep` reads no blockers (it closes delivered jobs), so a report of
"sweep refused on a blocker" is not this cache. Wrong comments naming sweep were
the review's F2; check the caller in the code before crediting a verb.

*Anchors: `tools/fabric/jobsparts/blockers.py::refresh`, `tools/fabric/jobsparts/needs.py::_blockers_cleared`*

*Observed 2026-11-09 (python-dev)*
