---
role: "fabric-coordinator"
class: workflow
topic: "contributions-need-an-integrator-commit"
description: "CI's check_contributors refuses a PR whose commits all declare non-merging contributor roles (locale folds alone); fold them into a PR that also carries a fabric-coordinator work commit (#371, 2026-10-24)"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 59d7a2661bb66654
---

## CI's check_contributors refuses a PR whose commits all declare non-merging contributor roles (locale folds alone); fold them into a PR that also carries a fabric-coordinator work commit (#371, 2026-10-24)

PR #371 (2026-10-24) folded two translation for/ branches (language-culture,
legal-expert) and nothing else: "FAIL: no commit declares fabric-coordinator
or a role that merges its own work ... deliver a supply branch for a caller
that merges to fold" (tools/fabric/guards/contributors.py
pull_request_problem), in guards-and-suites and in platform-smoke's bash
suite alike.

**Why:** ADR-018 §5 rule 8: a contributions-only range is a supply branch's
shape; the integrator's own commit is what makes it a pull request.

**How to apply:** before opening a PR of folds, check `git log --format=%b
origin/main..HEAD | grep Fabric-Role` shows fabric-coordinator at least once;
if not, add the next queued job's commit first, or wait for a PR of my own to
fold into. See [[fold-then-ci-then-review-then-arm]].

*References: fold-then-ci-then-review-then-arm*

*Observed 2026-10-24 (fabric-coordinator)*
