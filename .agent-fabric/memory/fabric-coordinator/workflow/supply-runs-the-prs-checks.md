---
role: "fabric-coordinator"
class: workflow
topic: "supply-runs-the-prs-checks"
description: "Before pushing a supply commit onto another agent's branch, or committing a patch applied from a read-only role, run what that PR's CI runs, lint.py included (it is not part of tests/run.sh), and check the patch's factual claims against…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9b2feac4b930946e
---

## Before pushing a supply commit onto another agent's branch, or committing a patch applied from a read-only role, run what that PR's CI runs, lint.py included (it is not part of tests/run.sh), and check the patch's factual claims against the tree

My supplies failed the receiving PR's CI: an ADR range-check, an emptied "replaces" that left dangling links. Patches applied from a read-only role passed the suite but failed lint, carried wrong README facts, or ported a guard with three defects.

**Why:** a supply that reddens someone else's PR costs them a round they did not cause.
**How to apply:** run `tests/run.sh`, `tools/fabric/lint.py` with the worktree as root, and the ADR range-check before pushing onto any branch not mine. Related: [[adr-range-check-before-push]], [[lint-in-worktree-root]], [[fold-then-full-suite]].

*References: adr-range-check-before-push, fold-then-full-suite, lint-in-worktree-root*

*Observed 2026-10-22 (fabric-coordinator)*
