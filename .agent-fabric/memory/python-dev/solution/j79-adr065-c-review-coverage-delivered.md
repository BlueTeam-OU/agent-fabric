---
role: "python-dev"
class: solution
topic: "j79-adr065-c-review-coverage-delivered"
description: "j79 ADR-065 C posting side delivered on for/user/j333-review-coverage; where things are, traps met"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - df49da52a1af1628
---

## j79 ADR-065 C posting side delivered on for/user/j333-review-coverage; where things are, traps met

j79 built the v2 review marker (base/head/card/config), the coverage block parser (tools/fabric/github/review_coverage.py, one parser for post_review and every reader), the `partial` bucket in classify, results.covers_head, review_checkpoint.last_checkpoint and review_codex's coverage path. Branch develop-qzapp/python-dev-02/for/user/j333-review-coverage, folded into #358 (e98470d5). Follow-up j80 = test_review_codex against the schema that now requires `coverage`.

**Why/traps:** a new module in arm.py's import closure must be added to projects/agent-fabric/integration/gh/arm.json (coordinator's) or test_arm_fabric_config, lint and two more suites fail; lint refuses `$` in a regex used with .match (use fullmatch); a Supplier-Review trailer needs a real staged change to amend (the hook refuses an empty amend); to verify against a coordinator's unmerged branch, merge it on a scratch local branch and delete it after.
**How to apply:** when touching the marker or block, change review_coverage.py only; mutation list lives in the session scratchpad, not the tree.

*Observed 2026-10-23 (python-dev)*
