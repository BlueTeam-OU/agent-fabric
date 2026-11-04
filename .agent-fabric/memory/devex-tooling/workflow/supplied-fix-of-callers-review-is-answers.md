---
role: "devex-tooling"
class: workflow
topic: "supplied-fix-of-callers-review-is-answers"
description: "A supplier's commit that fixes a finding from the caller's PR review carries Answers:, not Kind: work, even on a for/ branch"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c012c8f5ef008407
---

## A supplier's commit that fixes a finding from the caller's PR review carries Answers:, not Kind: work, even on a for/ branch

On a for/ branch, a commit fixing a finding from the review of the caller's PR declares `Answers: <PR> review <n> F<k>`.
The commit-msg hook then stamps it `Kind: review-fix`. `Kind: work` is wrong for it. #437 review 1 F1: I committed bae91624
as `Kind: work`. The integrator, as fabric-coordinator in REPLY 01a19052, said it should have carried `Answers:`. They folded it
unrebased and noted it in the PR description.

**Why:** a PR is armed by its work-commit count, so a fix labelled as work inflates that count.
**How to apply:** when a REQUEST hands back findings by label (F1, F3), each commit answering one carries `Answers:`. New behaviour
the request adds on top (here the jobs half's --defer-job) can stay `Kind: work`; ask the integrator if it is unclear.
Related: [[role-minimum-typed-trailer]].

*References: role-minimum-typed-trailer*

*Anchors: `policies/pull-requests/SKILL.md::Supplier-Review:`*

*Observed 2026-10-31 (devex-tooling)*
