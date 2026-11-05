---
role: "fabric-coordinator"
class: workflow
topic: "next-work-rides-the-open-pr"
description: "One open PR per repo means the next ready piece of work is folded onto it as more commits, not held until it merges; owner caught j509 waiting on #451 (2026-11-01)"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1ecc91be133f03da
---

## One open PR per repo means the next ready piece of work is folded onto it as more commits, not held until it merges; owner caught j509 waiting on #451 (2026-11-01)

On 2026-11-01 the owner asked why I had not folded j509 (python-dev-01's for/ branch, ready since 13:09Z) into #451, which was still open and being reviewed. I had read "one open PR per agent and repository" as a reason to wait for #451 to merge. The charter says the opposite: one PR open at a time, and the next piece of work is another commit on it, never a PR per topic.

**Why:** holding ready work behind an open PR serialises the fleet. The supplier (python-dev-01) waited, and the owner had to ask.

**How to apply:**
- When a supply or my own next job is ready while my PR is open in that repository, fold it onto that PR's branch right away. Then run the suite and get a blind review of its range before arming.
- The fold has to happen in the PR's job copy (one-job guard), so switch to that job or ask the owner which way.
- Ask before folding only when the PR is already armed: a push disarms it, and the owner decides whether to delay the merge. On 2026-11-01 the owner chose to let #451 merge and open j509 next.

Related: [[owner-bug-list-after-j509]], [[supply-onto-pr-branch-in-job-copy]].

*References: owner-bug-list-after-j509, supply-onto-pr-branch-in-job-copy*

*Anchors: `identities/roles/fabric-coordinator/charter.md::the next piece of work another commit on it`*

*Observed 2026-11-01 (fabric-coordinator)*
