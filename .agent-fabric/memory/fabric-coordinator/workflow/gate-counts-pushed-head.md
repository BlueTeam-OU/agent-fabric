---
role: "fabric-coordinator"
class: workflow
topic: "gate-counts-pushed-head"
description: "fabric-pr gate counts the PR's pushed head; a local unpushed commit is not in its W/F numbers"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d8cde1603de456ae
---

## fabric-pr gate counts the PR's pushed head; a local unpushed commit is not in its W/F numbers

`fabric-pr gate <N>` reads the PR's head on GitHub, so a commit made locally and not yet pushed is missing from its "(W work, F fix)". On 2026-10-31 I gave #437 as "3 work" from memory while the gate said 4 pushed (5 with my local j452 commit); the pr-counts Stop hook caught the missing counts.

**Why:** the owner arms from the counts I state, and the hook demands them from the gate, not from my reckoning.
**How to apply:** state the gate's numbers with the head sha, and say separately what is local and unpushed ("4 work at 9c439b8e; 5 once pushed"). Related: [[pr-counts-for-every-pr-named]].

*References: pr-counts-for-every-pr-named*

*Anchors: `tools/fabric/github/pr_gate.py`*

*Observed 2026-10-31 (fabric-coordinator)*
