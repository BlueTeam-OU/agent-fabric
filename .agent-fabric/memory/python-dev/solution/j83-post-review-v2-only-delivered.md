---
role: "python-dev"
class: solution
topic: "j83-post-review-v2-only-delivered"
description: "j83 #358 round 1 delivered on for/user/j333-review-coverage 534b81eb; post_review is v2-only, base tied to PR; suite traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8f51e70df9815434
---

## j83 #358 round 1 delivered on for/user/j333-review-coverage 534b81eb; post_review is v2-only, base tied to PR; suite traps

post_review (tools/fabric/github/post_review.py) refuses any report without a v2 header and block, reads the assembled body back with review_coverage.read_review, and ties the base to the PR (merge-base via `gh api compare` or last_checkpoint_review head). Delivered 534b81eb on develop-qzapp/python-dev-02/for/user/j333-review-coverage (worktree agent-fabric-j83-...).

**Why:** ADR-065 §5 rule 4 keeps v1 readable, never writable.
**How to apply:** every suite that mocks gh for post-review (test_post_review_cli, test_review_codex, test_review_gateway) needs baseRefName in pr.json plus a `/compare/` answer; test_post_review_cli auto-prefixes a v2 header and coverage block in `invoke`. A suite naming AGENT_FABRIC_ROOT must call own_instance_tree() (test_own_instance_tree scans text). Commit-hook guard refuses `git commit` commands containing $HOME; use plain paths. Mutation runs: TMPDIR of their own, kill checked against both test_post_review and the cli suite.

*Observed 2026-10-23 (python-dev)*
