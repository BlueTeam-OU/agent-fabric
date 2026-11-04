---
role: "python-dev"
class: workflow
topic: "mutation-run-needs-free-disk-first"
description: a mutation run on a full disk truncates the source when its restore cannot write — check df and keep the committed copy before planting
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2922313cd9563842
---

## a mutation run on a full disk truncates the source when its restore cannot write — check df and keep the committed copy before planting

On 2026-10-20 /home on develop-qzapp had 470 MB free; a mutation run's restore step
could not write and left four source files in a worktree truncated (restored from the
commit, nothing lost). The fleet-wide disk broadcast of 2026-10-24 showed the volume
is shared and fills again.

**Why:** a restore that writes through the same full volume fails after the mutation
has already been written, so the file stays mutated or empty.

**How to apply:** `df -h /home /var/tmp` before a mutation round, and plant only on
committed state (or a backup copy held on the same free volume) so `git restore` or
`cp` can bring the file back; check the file's size and `git diff --stat` after the
round. See [[suite-red-check-df-first]] and [[never-restore-a-mutation-with-git-checkout]].

*References: never-restore-a-mutation-with-git-checkout, suite-red-check-df-first*

*Observed 2026-10-25 (python-dev)*
