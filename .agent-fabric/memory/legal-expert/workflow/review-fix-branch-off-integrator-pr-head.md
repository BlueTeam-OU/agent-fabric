---
role: "legal-expert"
class: workflow
topic: "review-fix-branch-off-integrator-pr-head"
description: "Which base a contributor's review-fix for/ branch takes when its files exist only on the integrator's open PR"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "legal-expert-ee-eu"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6a5867bf94d3261f
---

## Which base a contributor's review-fix for/ branch takes when its files exist only on the integrator's open PR

My docs/legal/ files reach main folded into fabric-coordinator's PR. A review finding on them is fixed as one review-fix commit (trailer `Answers: <findings>`) on a fresh `<host>/<login>/for/user/<what>-review-<n>` branch, no PR. Until that PR merges, the files exist only on its branch: the fix branch goes off the PR's current head, not origin/main, or the commit re-adds the files whole. If the request said origin/main, I branch off the head anyway and name the deviation and the base commit in the REPLY.

**Why:** round 1 of a review asked for origin/main; I used the PR head and said why, and round 2's request itself named the PR head as base.

**How to apply:** before branching for a review fix, check `git ls-tree origin/main -- <my paths>`; if empty, base on the PR head the request names (or `gh pr view <n> --json headRefOid`).

*Anchors: `policies/authority.json::docs/legal/`*

*Observed 2026-10-18 (legal-expert)*
