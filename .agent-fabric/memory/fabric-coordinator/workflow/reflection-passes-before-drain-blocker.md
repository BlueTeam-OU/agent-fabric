---
role: "fabric-coordinator"
class: workflow
topic: "reflection-passes-before-drain-blocker"
description: "a drain job blocked on \"the week's reflection passes\" waits forever unless I issue them; run fabric-reflect-jobs first, block on a checkable job"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 73f02ba97c917cb4
---

## a drain job blocked on "the week's reflection passes" waits forever unless I issue them; run fabric-reflect-jobs first, block on a checkable job

On 2026-10-25 j279 (the next drain) was taken up blocked on "the 2026-W43
reflection passes" in free text, yet `bin/fabric-reflect-jobs --dry-run`
showed "would add" for all 30 logins: nobody had issued them, so the
blocker could never clear. Ran `bin/fabric-reflect-jobs` (W43, mine j393).

**Why:** ADR-058 puts issuing the weekly pass on the coordinator; a
free-text blocker is not checked by anything, and `fabric-jobs switch`
refuses to leave a job blocked on free text anyway.

**How to apply:** at the start of each ISO week, run `bin/fabric-reflect-jobs`
before taking a drain job; block the drain with `--on job:user/<my pass>`
(checkable). My own pass done does not clear the drain: on 2026-10-25,
three hours after issuing, 23 of 30 lists still held W43 queued. Count
`Reflection pass <week>` rows in `fabric-ctl all jobs`, re-block the drain
with one `--on job:<login>/j<n>` per open pass, and switch away; at the end
of the ISO week, passes still open are skipped (unblock and drain), never
waited on past it. See [[memory-work-closed-2026-10-14]].

*References: memory-work-closed-2026-10-14*

*Anchors: `bin/fabric-reflect-jobs`, `memory/README.md::The reflection pass comes first`*

*Observed 2026-10-25 (fabric-coordinator)*
