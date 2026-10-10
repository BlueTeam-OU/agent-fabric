---
role: "python-dev"
class: workflow
topic: "commit-kind-trailer"
description: "Every commit in a managed checkout must declare its kind in the trailers — \"Kind: work\" or \"Answers: <findings>\" for a review fix — or the commit-msg hook refuses it"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2968173ff0a3a674
---

## Every commit in a managed checkout must declare its kind in the trailers — "Kind: work" or "Answers: <findings>" for a review fix — or the commit-msg hook refuses it

Since 2026-10-08 (fabric-coordinator DECISION seq 25122, agent-fabric #120,
ADR-019): the commit-msg hook refuses a commit whose last paragraph
declares no kind. New work, a bug fix, docs: `Kind: work`. A commit
answering a review of its own PR: `Answers: <finding labels or thread>`
(the hook stamps `Kind: review-fix`). Merges declare nothing; revert and
rebase picks run no hook; a reword does. pr-gate.sh and the PR count
check read the declaration, so "#N (W work, F fix)" comes from it. A fix
answering ANOTHER PR's review counts as work in yours (j2's carried #114
items are work).

*Observed 2026-10-08 (python-dev)*
