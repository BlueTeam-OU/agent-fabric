---
role: "python-dev"
class: domain
topic: "review-before-suite-and-numeric-guards"
description: "ordering a delivery's checks (review, then the full suite) and guarding numbers parsed from JSON or argv in Python"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5e1aec202ef2fafb
---

## ordering a delivery's checks (review, then the full suite) and guarding numbers parsed from JSON or argv in Python

Two lessons from j38, the actions-health port (branch
for/user/actions-health, 2026-10-06):

- **Run the full suite after the review, not beside it.** Three times in
  one day I started `tests/run.sh` and the blind review together. The
  review found something, I edited the tree under the running suite, and
  I had to stop it and run it again. Each stopped run cost 20 minutes or
  more. The review takes 2 to 6 minutes. So: mutations first, then
  review, then fix and re-review, and the suite last, once, on the final
  head.
- **A number from JSON or argv needs one finite() check, not scattered
  ones.**
  - `math.isfinite(huge_int)` raises OverflowError, not ValueError.
  - `json.loads` accepts NaN and Infinity.
  - A sum of finite values can overflow to inf.
  - Python's `\d` matches non-ASCII digits, and `int("٣٠٠٠")` is 3000.

  One helper turns each into ValueError: `float(v)` inside a try that
  catches OverflowError, then `isfinite`. Apply it to each value and
  each sum, and match digits with `[0-9]`. A catch-all that maps an
  unforeseen error to "could not find out" (exit 2) keeps a traceback
  from passing for the "degraded" exit 1. Test it with a real hostile
  input; a body nested too deeply for `json.loads` raises
  RecursionError, which escapes gh.py.

**Why:** two review rounds each found one more member of this class.
**How to apply:** at the first numeric guard, write finite() and route
every number through it. See [[python-defaults-that-differ-from-node]].

*References: python-defaults-that-differ-from-node*

*Observed 2026-10-06 (python-dev)*
