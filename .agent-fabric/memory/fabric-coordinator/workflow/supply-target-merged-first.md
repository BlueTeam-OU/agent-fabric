---
role: "fabric-coordinator"
class: workflow
topic: "supply-target-merged-first"
description: a supply job whose target PR merged before I supplied — check gh pr view state first; the deferred finding lands as my own PR off main
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b7e15b6309a4aac4
---

## a supply job whose target PR merged before I supplied — check gh pr view state first; the deferred finding lands as my own PR off main

j819 (2026-11-14): the job said "supply CARRIER-CONTRACT §4/§5 onto python-dev-04's #585 branch",
but #585 had merged at arm with ae933850:F1 deferred. First call of a supply job:
`gh pr view <n> --json state`. If MERGED, the fix is my own PR on the job branch off main
(#596), and a REPLY tells the contributor their branch needs nothing more.

Lesson from #596's three review rounds: a doc fix for one finding must re-check *every*
host/addressing claim in the document against the code (round 1 caught §1 "loopback only",
false since d7373c52; round 2 caught my new wording's "same host" ambiguity). Brief the
reviewer with "every other statement about X stays true of the code" as a requirement.

The code's two notions of "same host" (roster.py:358 own-row host vs engine.py:121 identity
host) plus IPv4 loopback for an ip6 host and no-host rows in a multi-host fleet: j859, for
the python-dev holder of W10. See [[supply-onto-pr-branch-in-job-copy]].

*References: supply-onto-pr-branch-in-job-copy*

*Anchors: `tools/fabric/gzcoord/carrier/roster.py::render_config`, `tools/fabric/gzcoord/carrier/engine.py::row_host`*

*Observed 2026-11-14 (fabric-coordinator)*
