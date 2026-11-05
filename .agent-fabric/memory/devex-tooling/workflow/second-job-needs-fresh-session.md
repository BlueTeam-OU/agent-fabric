---
role: "devex-tooling"
class: workflow
topic: "second-job-needs-fresh-session"
description: "a follow-up REQUEST arriving after a delivery: the job guard refuses its commit in the session that worked the first job; save the diff under $XDG_RUNTIME_DIR, ack, pause with a note, fabric-fresh --job"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 107cdafb27bac08c
---

## a follow-up REQUEST arriving after a delivery: the job guard refuses its commit in the session that worked the first job; save the diff under $XDG_RUNTIME_DIR, ack, pause with a note, fabric-fresh --job

After j275 was delivered, #465's round-2 REQUEST (j276) arrived in the same session. I wrote the fix
and its test in place; `git commit` was refused by the PreToolUse job guard ("This session worked job
j275 ... j276 belongs to a fresh session", agent-fabric ADR-037 rule 3), reading the copy is allowed.

**Why:** one job per session; the guard keys on jobs worked, not on the working copy or branch.
**How to apply:** on a new REQUEST after a delivery, start it only to read and plan. If the work is
already written: `git diff --binary > $XDG_RUNTIME_DIR/<job>/x.diff`, restore the copy, send a REPLY
naming the branch (switch refuses while a REPLY-EXPECTED is unanswered), `fabric-jobs pause <job>
"<note naming the diff>"` (switch refuses while it is active), `fabric-jobs switch`, then
`fabric-fresh --job <job>`. Related: [[job-guard-judges-session-cwd]].

*References: job-guard-judges-session-cwd*

*Observed 2026-11-03 (devex-tooling)*
