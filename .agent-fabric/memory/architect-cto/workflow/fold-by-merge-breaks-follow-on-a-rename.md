---
role: "architect-cto"
class: workflow
topic: "fold-by-merge-breaks-follow-on-a-rename"
description: "A branch that renames a file must not fold origin/main by merge while main still has a file under the renamed-to name; git log --follow loses the history. Rebase instead, and measure in a scratch clone."
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b1d23bece7fd1743
---

## A branch that renames a file must not fold origin/main by merge while main still has a file under the renamed-to name; git log --follow loses the history. Rebase instead, and measure in a scratch clone.

Measured on gzapp #1114 (2026-10-13, CLAUDE.md => AGENTS.md while main still carried an old adapter AGENTS.md): after `git merge origin/main` into the branch, `git log --follow AGENTS.md` printed 3 commits at the head (the adapter's history) against 205 before the fold; the same commits rebased onto origin/main gave 205 under both a `--no-ff` merge into main and a fast-forward (scratch `git clone --shared --no-checkout`). The fix was a rebase with `--force-with-lease`, which the auto-mode classifier refuses to a session: the owner ran it from `! ~/<script>.sh`, and the OpenTimestamps commit hook stalled it twice (needs 2 attestations) until `git rebase --continue` was retried.

**Why:** `--follow` is single-path rename tracking; at a merge whose other parent holds a different file under the new name it follows that file's creation instead of the rename.

**How to apply:** on a branch with a rename, bring in main with `git rebase origin/main`, never a merge; write `fabric-review` requests with the head as a commit id (not HEAD) so `fabric-review next` can derive the re-review; state the measured follow count in the PR body. See [[gzapp-open-items]].

*References: gzapp-open-items*

*Observed 2026-10-13 (architect-cto)*
