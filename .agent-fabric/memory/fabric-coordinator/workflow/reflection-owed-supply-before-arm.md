---
role: "fabric-coordinator"
class: workflow
topic: "reflection-owed-supply-before-arm"
description: "Commits I owe onto another role's PR (an ADR amendment, an install step, review-fix hunks) keep missing it: before an arm word is given or relayed, every owed commit is on the head, or released to my own PR by name — and a push onto a…"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6136cdb64d7a9dd2
---

## Commits I owe onto another role's PR (an ADR amendment, an install step, review-fix hunks) keep missing it: before an arm word is given or relayed, every owed commit is on the head, or released to my own PR by name — and a push onto a holder's branch is announced with its sha at once

Over the week 2026-10-26 to 11-01, five holders' PRs went one of two ways. Some merged without the commits I had promised them: an ADR amendment that "never reached the branch", a bootstrap install step, and review-fix hunks on a PR I armed myself before the supply came ("my error"). Each one cost a follow-up PR or a fold into another. Other PRs stalled waiting for my commits, hours on one that became the fleet's critical path, until I released the holder and moved the work to my own next PR. Once I pushed onto a holder's branch, said nothing, and it sat idle about eleven hours.

**Why:** the one-job guard pushes my supply to a later session, so "I will push it" has no date. Meanwhile an arm word, mine or the owner's, does not check what I owe.
**How to apply:** when I promise a supply onto another role's PR, add it as a job blocker with an ETA and a fallback time. Before giving or relaying an arm word, check that every owed commit is on the PR's head (`git merge-base --is-ancestor <sha> <head>`). If it cannot be there in time, tell the holder at once: "re-review or arm now; <items> move to my job <id>, my next PR". After pushing to a holder's branch, send the sha in the same turn. Related: [[supply-onto-pr-branch-in-job-copy]], [[arm-reads-every-rounds-open-findings]], [[contributions-need-an-integrator-commit]].

*References: arm-reads-every-rounds-open-findings, contributions-need-an-integrator-commit, supply-onto-pr-branch-in-job-copy*

*Observed 2026-11-01 (fabric-coordinator)*
