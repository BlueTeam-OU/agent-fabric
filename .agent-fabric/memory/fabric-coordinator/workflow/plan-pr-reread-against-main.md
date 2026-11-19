---
role: "fabric-coordinator"
class: workflow
topic: "plan-pr-reread-against-main"
description: "before opening a PR for a plan written a day earlier: re-read every code claim against origin/main and list for/<me>/ branches; #604 shipped a plan whose W3/W5/W10/W12/W14 had merged and missed a waiting W4 supply"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - afe9e5e92a3fe89e
---

## before opening a PR for a plan written a day earlier: re-read every code claim against origin/main and list for/<me>/ branches; #604 shipped a plan whose W3/W5/W10/W12/W14 had merged and missed a waiting W4 supply

j814 pushed the cutover plan (77f368b9, written 2026-11-13 against 8c3613b1) a day later as #604. Round 1 of the blind review found that #573, #581 (W3), #584 (W5), #585 (W10), #586 (W12) and #587 (W14) had all merged in between, and that control was already on `dual`. My new ADR-041 rule 7 also contradicted the code, because devex-tooling's W4 had been waiting unfolded on `develop-qzapp/devex-tooling/for/user/w4-arm-journal-grant`. It took four review rounds.

**Why:** the work items were dispatched the same day the plan was written, so the plan went stale within hours. A rule amended from the plan, not from the code, describes neither.

**How to apply:**
- Before opening a PR for a plan or record written in an earlier session, `git log --merges <plan-base>..origin/main` and re-read each claim the plan makes about code.
- `git ls-remote origin '*for/user*'` first: fold a waiting supply before writing the rule it implements.
- Amend a record to what the code on the head does. Name which conditions are the owner's and which are mine, with the commit that first carried each.

Related: [[interweave-only-cutover-owner-decisions]], [[supply-target-merged-first]].

*References: interweave-only-cutover-owner-decisions, supply-target-merged-first*

*Observed 2026-11-14 (fabric-coordinator)*
