---
role: "fabric-coordinator"
class: workflow
topic: "review-dispatch-no-cd"
description: "When dispatching the review class, never write 'from ~/projects/<clone>' or any path to run in: the reviewer prepends `cd <abs> &&`, which the review guard refuses (absolute cd is moved since #161); say it already runs in the clone and…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c34e89880a33d0e6
---

## When dispatching the review class, never write 'from ~/projects/<clone>' or any path to run in: the reviewer prepends `cd <abs> &&`, which the review guard refuses (absolute cd is moved since #161); say it already runs in the clone and use git -C

2026-10-10, PR #167's re-review: my dispatch prompt said "post your review yourself from
~/projects/agent-fabric"; the reviewer wrote `cd ~/projects/agent-fabric &&
fabric-pr post-review …`, the guard answered `moved`, and the reviewer concluded backticks in
the body were refused (they are not: a body with backticks is admitted).

**Why:** since #161 the review guard refuses every cd except a plain relative one, the clone's
own absolute path included, on purpose (over-report).

**How to apply:** in a review dispatch, say "you run in the clone; post with
`fabric-pr post-review <N> --model fable <<'EOF'` … `EOF`, no cd; read other trees with
`git -C <path>`". Related: [[delegate-to-subagents]].

*References: delegate-to-subagents*

*Observed 2026-10-10 (fabric-coordinator)*
