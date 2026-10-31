---
role: "devex-tooling"
class: workflow
topic: "dependabot-pr-review-posters"
description: "a blind review posted on a Dependabot PR is \"marked, other login\" and not coverage until AGENT_FABRIC_REVIEW_POSTERS names the session push account"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 93d4358a058d9204
---

## a blind review posted on a Dependabot PR is "marked, other login" and not coverage until AGENT_FABRIC_REVIEW_POSTERS names the session push account

On a Dependabot PR the PR author is the bot, so `fabric-pr post-review` posts fine but review-status lists the review as "marked, other login" (not coverage), and `fabric-pr arm` refuses on a security-boundary file (`.github/workflows/`). Nothing in the tree sets AGENT_FABRIC_REVIEW_POSTERS. Fix for the gate/arm calls: `export AGENT_FABRIC_REVIEW_POSTERS='["andreabenetton"]'` (the account sessions push as, `gh api user`). Arm also needs `--any-owner` (the branch names no session). Seen on agent-fabric #266, j211, 2026-10-24; merged 2d783280. Related: [[review-post-no-repo-flag]].

*References: review-post-no-repo-flag*

*Anchors: `tools/fabric/github/review_status/verdicts.py::cfg.review_posters`*

*Observed 2026-10-24 (devex-tooling)*
