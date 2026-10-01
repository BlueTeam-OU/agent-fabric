---
role: "fabric-coordinator"
class: workflow
topic: "cross-repo-lint-window"
description: "A fabric push that changes what a project's index must list reddens that project's queue until its index PR merges — hold the push for a quiet queue until fabric-ref is live; and never chain a commit behind a piped test run"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - 5cde1d6dd05d73c9
---

## A fabric push that changes what a project's index must list reddens that project's queue until its index PR merges — hold the push for a quiet queue until fabric-ref is live; and never chain a commit behind a piped test run

Four times on 2026-09-18 a gzapp required check went red because
agent-fabric main moved under `_ban-checks.yml`'s unpinned checkout —
the last one (the language-culture brief, 695a75e) after I had written
the landing rule and said the window would be "minutes"; #855's queue
run landed inside those minutes. The CEO: "all time the same error …
did you learn?"

**Why:** the corpus lint reads two repositories at their heads, and the
order is forced (an index listing a slice not yet on fabric main is the
same finding), so sequencing shortens the window and never closes it;
only the pin closes it (`.agent-fabric/fabric-ref` + the project's
checkout step, gzapp#854/#857). Also: `python3 tests/x.py | tail &&
git commit` commits on tail's exit status — dc61f19 went to main with a
failing case that way.

**How to apply:** until the pin is live on a project's main, a fabric
push that changes what that project's index must list waits for an
empty merge queue and goes out with the index PR in the same minute;
with the pin live, the ref moves in the index PR and the push is free.
Never put a pipe between a test run and the `&&` that commits — run the
suite to a file and test its exit. Register a new `case_` in the
suite's `main()` list (test_lint.py collects by list, not by name).
See [[blind-review-loop]].

*References: blind-review-loop*

*Observed 2026-09-18 (fabric-coordinator)*
