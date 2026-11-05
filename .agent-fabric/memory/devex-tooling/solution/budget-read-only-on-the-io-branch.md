---
role: "devex-tooling"
class: solution
topic: "budget-read-only-on-the-io-branch"
description: a time budget read eagerly at a call site fails rows that never do I/O; pass budget.left as a callable, ask it on the branch that calls out
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f91c49e67403b0a8
---

## a time budget read eagerly at a call site fails rows that never do I/O; pass budget.left as a callable, ask it on the branch that calls out

In agent-fabric, `pr_counts.describe` called `engines_unavailable(pr, budget.left())`. `Budget.left()` raises
Unreadable once the budget is spent, so a person's PR, which asks GitHub nothing there, became "cannot be read" near
the deadline (#465 r2 F8). Fix 464abb1c, on for/user/j276-465-r2-f8: pass `budget.left` and call it only under
`review_posters.is_bot(author)`. To test it, give `Budget(5, clock=...)` a clock that is already spent, then assert
that the person's row keeps its line and the app's row is "cannot be read".

**Why:** the deadline belongs to the I/O, not to the row. When the budget is read eagerly, a row built from data
already fetched fails.
**How to apply:** for any `timeout=budget.left()` argument, check whether the callee always does I/O. If it does
not, pass the callable. Related: [[one-format-one-parser]].

*References: one-format-one-parser*

*Anchors: `tools/fabric/github/pr_counts.py::engines_unavailable(pr`, `budget.left)`*

*Observed 2026-11-03 (devex-tooling)*
