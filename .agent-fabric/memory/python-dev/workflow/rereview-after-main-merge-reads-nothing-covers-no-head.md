---
role: "python-dev"
class: workflow
topic: "rereview-after-main-merge-reads-nothing-covers-no-head"
description: "a re-review whose fix range includes a merge of origin/main lists the merged files as \"not read\" and the gate refuses to count it; do the merge before the last fixes and review origin/main..HEAD once"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c475d4ed469f394b
---

## a re-review whose fix range includes a merge of origin/main lists the merged files as "not read" and the gate refuses to count it; do the merge before the last fixes and review origin/main..HEAD once

#423 (j73, 2026-10-30): to render `fabric-review next` the branch had to contain
origin/main, so I merged it. The re-review's range then held ~13 files of other
agents' work, the reviewer reported them "not read", and `fabric-pr gate` /
`arm --dry-run` kept saying the head had no counted review although the report
was posted.

**Why:** the coverage block requires every path of `git diff --name-only` for the
range; "not read" on any path voids coverage of the head.

**How to apply:** merge origin/main *before* the last fix commits, make all fixes,
run the full suite alone (a concurrent reviewer made one timing test flake), then
one fresh `fabric-review brief` with `range: origin/main..HEAD` and the scope
listing every changed file; post that report on the head. Also: the sandbox
reviewer's `out_of_scope` must not repeat scope paths (a blind sed on `scope: [`
also hit `out_of_scope: [`). [[review-report-post-extract-from-transcript]]

*References: review-report-post-extract-from-transcript*

*Observed 2026-10-30 (python-dev)*
