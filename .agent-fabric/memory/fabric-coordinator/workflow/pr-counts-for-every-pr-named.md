---
role: "fabric-coordinator"
class: workflow
topic: "pr-counts-for-every-pr-named"
description: "before a reply that names any #N — merged, another agent's, or one cited in passing — read fabric-pr gate for each and write \"#N (W work, F fix)\""
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2a8865cf04aaff98
---

## before a reply that names any #N — merged, another agent's, or one cited in passing — read fabric-pr gate for each and write "#N (W work, F fix)"

The pr-counts stop hook (`runtime/claude-code/hooks/pr-counts.py`) refuses a
reply that names a pull request without "(W work, F fix)", and it counts every
#N that resolves to a PR: merged ones (#423, #428, #425, #414 on 2026-10-30),
another agent's, and one mentioned only as history ("#425 merged with F5 open").
On 2026-10-30 (j467) it sent me back four times in one session.

**Why:** the owner decides arming from what I say; a status without counts is
not one they can act on, and the hook does not distinguish open from merged.
**How to apply:** draft the reply, list every `#N` in it, run
`fabric-pr gate N | head -1` for each in one call from the project's working
copy, then write each as "#N (W work, F fix)" before sending. Related:
[[arming-prs]].

*References: arming-prs*

*Anchors: `runtime/claude-code/hooks/pr-counts.py`*

*Observed 2026-10-30 (fabric-coordinator)*
