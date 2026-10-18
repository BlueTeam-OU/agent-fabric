---
role: "architect-cto"
class: domain
topic: "antique-anthropic-code-review-surface"
description: "Antique is Anthropic's internal code review surface (2026), beside Scion source control; what is public about it and what is not"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 15157b3cfedff189
---

## Antique is Anthropic's internal code review surface (2026), beside Scion source control; what is public about it and what is not

Antique is Anthropic's internal code review tool, named in the engineering post "Redesigning source control at Anthropic" (2026-10-13, https://www.anthropic.com/engineering/redesigning-source-control). It was built by the same seven-person team as Scion (centralised, server-side version control that replaced git in their monorepo) in five months, together with code search and a source-control IAM system. The owner raised it on 2026-10-15 as something outside our tree.

Public facts (the post, plus Simon Willison's chart reading): Antique "change requests" replaced pull requests internally between late May and mid-July 2026; it has a merge queue with no global lock (conflicts are caught by post-merge and pre-deploy testing, and fixed by Claude); its approval rules "can express complex semantic constraints on approvals", so comment-only changes are separated from sensitive logical changes and human reviewers review intent rather than every line; Anthropic "makes extensive use of adversarial review", not tied to Antique in the text. Volume context: monorepo merges grew from about 2,500 to over 30,000 a day.

Not public: who reviews (humans vs agents), stacking, review cost or token accounting, how a review gates a merge. Nothing to copy from it yet for [[review-economics-measured-2026-10-14]]; the one transferable idea is approval constraints that classify a change by what it touches, which our arming policy does only by work-commit count and security-boundary paths.

*References: review-economics-measured-2026-10-14*

*Observed 2026-10-15 (architect-cto)*
