---
role: "fabric-coordinator"
class: workflow
topic: "rule-change-restatement-sweep"
description: "When a rule, tool or note is retired, renamed or built, sweep every restatement in the same pass: project CLAUDE.md, hook text, skills, remits, ADR status lines ('not yet built'), locale mirrors, and drained slices (a correction from…"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2e9abffbb4465633
  - 80c6b56a170be5b5
---

## When a rule, tool or note is retired, renamed or built, sweep every restatement in the same pass: project CLAUDE.md, hook text, skills, remits, ADR status lines ('not yet built'), locale mirrors, and drained slices (a correction from their author)

Retirements left stragglers that blind reviews found one at a time: nine gzapp slices still teaching the retired reviewer flow, two gzapp texts with the old arming rule, a remit naming a closed stage as open, ADR rules still ending "Not yet built" after the build merged.

**Why:** each straggler is another PR, another review round, and a session acting on stale text meanwhile.
**How to apply:** before the change's first REQUEST batch, `git grep` origin/main of agent-fabric and every managed project for the old name and claim, include locales and remits, and put all of them in that batch. Remits state the function and point at the record; they never say a stage is open. Related: [[fix-a-claim-everywhere-it-is-made]], [[accepted-only-when-on-main]].

W44 (reflection 2026-W44) widened the trigger. A plain behaviour change to an existing verb leaves the same stragglers: ADR rule rows, schema descriptions, a skill, a docs page, an AGENTS.md line. Seven PRs merged with one of those stale, or were held at review by a P2 on it. The two PRs where I had supplied the texts on the branch before the review needed no follow-up. So the sweep runs when I write the REQUEST for any behaviour change, not only for a retirement, and its texts go on the branch before the blind review.

*References: accepted-only-when-on-main, fix-a-claim-everywhere-it-is-made*

*Observed 2026-11-01 (fabric-coordinator)*
