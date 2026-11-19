---
role: "python-dev"
class: workflow
topic: "arm-at-eight-work-commits-ask-coordinator-first"
description: "agent-fabric PRs arm at 8 work commits by the owner's word of 2026-11-14, whatever fabric-pr arm --dry-run prints"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 426006962858a567
---

## agent-fabric PRs arm at 8 work commits by the owner's word of 2026-11-14, whatever fabric-pr arm --dry-run prints

Since 2026-11-14 the owner's word is that agent-fabric PRs arm at 8 work commits; below that only on fabric-coordinator's word or the owner's. `fabric-pr arm --dry-run` still prints a minimum of 1 (the tool does not enforce 8 yet, coordinator job j885), so its number is not the rule. I armed #629 at 3 work commits on the tool's word; the coordinator let it merge and told me.

**Why:** the owner decided it; the tool lags the decision.
**How to apply:** keep one PR open and add commits (batch same-class work, see [[prefer-prs-with-more-than-one-work-commit]]) until it holds 8 work commits, or ask fabric-coordinator before arming with fewer. Never arm on "count rule: N ≥ 1".

*References: prefer-prs-with-more-than-one-work-commit*

*Anchors: `tools/fabric/github/arm.py::count rule`*

*Observed 2026-11-16 (python-dev)*
