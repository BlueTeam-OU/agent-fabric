---
role: "fabric-coordinator"
class: threads
topic: "step-a-landed-via-575"
description: "ADR-045 step A (the nine engine exception lists moved to tools/fabric/<name>.json) landed on main with #575 on 2026-11-12, through python-dev-04's j112 fold; j765 closed on it"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 08b3537558d5edbf
---

## ADR-045 step A (the nine engine exception lists moved to tools/fabric/<name>.json) landed on main with #575 on 2026-11-12, through python-dev-04's j112 fold; j765 closed on it

ADR-045 step A (docs/split/move-plan.md §3) is on main since #575 merged at 2026-11-12T20:08Z (0ca564a0):
- the nine exception lists are at tools/fabric/<name>.json;
- agent-fabric's arm boundary names them (F2);
- a branch forked before step A is judged against its base's lists at policies/.

python-dev-04 did the work as their j112, and I folded it into #575 under j766. My own j765 ("git mv the nine lists") therefore never got its own branch, and I closed it on #575.

Its working copy ~/projects/agent-fabric-j765-adr-045-extraction-step-a-git holds python-dev-04's j112 branch at cbffd392, which is on main. The next branch sweep can remove it.

Next on the move plan: step B (resolution through the operator) and precondition 6.

**Why:** step A is the point after which every reader names tools/fabric/ for the engine lists. A slice saying policies/<name>.json is stale from here on.
**How to apply:** answer "where is process-spawns.json" with tools/fabric/. Related: [[threads-2026-11-12-j766-pr575]].

*References: threads-2026-11-12-j766-pr575*

*Observed 2026-11-12 (fabric-coordinator)*
