---
role: "fabric-coordinator"
class: workflow
topic: "dependabot-pr-review-posters"
description: "Arming a Dependabot PR: my posted blind review reads 'marked, other login' (author is dependabot[bot]); set AGENT_FABRIC_REVIEW_POSTERS to the push account and arm --any-owner"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 449eaadbad4f7b05
---

## Arming a Dependabot PR: my posted blind review reads 'marked, other login' (author is dependabot[bot]); set AGENT_FABRIC_REVIEW_POSTERS to the push account and arm --any-owner

2026-11-01, #408/#409 (owner: "merge 408 and 409"): `fabric-pr post-review` posted the review-class review as
the account every session pushes as (`gh api user --jq .login`), but review-status put it under "marked, other login"
because the PR author is dependabot[bot] (tools/fabric/github/review_status/verdicts.py: posted = author or
cfg.review_posters). Arm refused "no review-class review of the current head". What worked:
`AGENT_FABRIC_REVIEW_POSTERS='["<push login>"]' fabric-pr arm --any-owner <n> --basis "..."`, merged both.
Without --any-owner arm refuses "not this session's" branch. A fix making the push account a poster by default is
job j527.

**Why:** Dependabot PRs are fabric-coordinator's to review and merge (policies/AUTHORITY.md).
**How to apply:** check the pins against `gh api repos/<action>/git/ref/tags/<tag>` before arming; a stale-base CI
run gets `@dependabot rebase` first.

*Anchors: `tools/fabric/github/review_status/verdicts.py::cfg.review_posters`, `tools/fabric/github/arm.py::AGENT_FABRIC_REVIEW_POSTERS`*

*Observed 2026-11-01 (fabric-coordinator)*
