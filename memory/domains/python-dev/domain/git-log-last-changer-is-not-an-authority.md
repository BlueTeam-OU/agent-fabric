---
role: "python-dev"
class: domain
topic: "git-log-last-changer-is-not-an-authority"
description: "\"which commit last changed this path\" as a trust anchor — git log -1 simplifies merges to one parent; --full-history over-lists and orders by dates the agent controls; walk parents instead"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4678909b8a1ec30f
---

## "which commit last changed this path" as a trust anchor — git log -1 simplifies merges to one parent; --full-history over-lists and orders by dates the agent controls; walk parents instead

When a check trusts "the commit that last changed path P" (a signature on
it, who made it), `git log -1 -- P` is not that commit. History
simplification follows only the parent whose version of P matches the
result, so an agent can commit-tree a merge M of HEAD and an older, signed
install O whose tree carries O's P: `log -1` names O, O's P equals HEAD's,
and the stale text passes. `--full-history` does not close it: it lists an
unrelated merge that equals one parent but not the other, `--parents`
rewrites a merge's parents, and "newest" is an order (dates, topology) the
agent writes.

**Why:** found in the holder-addenda loader (addenda.py, #290 round 2),
fixed by `_last_changer` (rev-list --parents, oldest first, one
`cat-file --batch-check` for P's oid per commit; a commit equal to all
parents inherits their answer, a version equal to only some parents counts
as a carry-over only if every merge base with the others holds that
version, else the merge itself is the change). `.git/shallow` and grafts
refused too: they cut the history the walk reads.

**How to apply:** compare the object ids of P itself (tree oid at HEAD vs
at the judged commit) as a second line, derive the answer per commit from
its parents' answers rather than from git's log output, and give the test
a merge repro plus an unrelated merge that must still load. Related:
[[reading-git-objects-under-a-hostile-git-dir]].

*References: reading-git-objects-under-a-hostile-git-dir*

*Observed 2026-10-22 (python-dev)*
