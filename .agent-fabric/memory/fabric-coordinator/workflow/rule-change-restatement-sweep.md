---
role: "fabric-coordinator"
class: workflow
topic: "rule-change-restatement-sweep"
description: "When a rule, tool or note is retired, renamed or built, sweep every restatement in the same pass: project CLAUDE.md, hook text, skills, remits, ADR status lines ('not yet built'), locale mirrors, and drained slices (a correction from…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 80c6b56a170be5b5
---

## When a rule, tool or note is retired, renamed or built, sweep every restatement in the same pass: project CLAUDE.md, hook text, skills, remits, ADR status lines ('not yet built'), locale mirrors, and drained slices (a correction from their author)

Retirements left stragglers that blind reviews found one at a time: nine gzapp slices still teaching the retired reviewer flow, two gzapp texts with the old arming rule, a remit naming a closed stage as open, ADR rules still ending "Not yet built" after the build merged.

**Why:** each straggler is another PR, another review round, and a session acting on stale text meanwhile.
**How to apply:** before the change's first REQUEST batch, `git grep` origin/main of agent-fabric and every managed project for the old name and claim, include locales and remits, and put all of them in that batch. Remits state the function and point at the record; they never say a stage is open. Related: [[fix-a-claim-everywhere-it-is-made]], [[accepted-only-when-on-main]].

*References: accepted-only-when-on-main, fix-a-claim-everywhere-it-is-made*

*Observed 2026-10-22 (fabric-coordinator)*
