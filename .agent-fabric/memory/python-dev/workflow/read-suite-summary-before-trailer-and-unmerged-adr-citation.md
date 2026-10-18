---
role: "python-dev"
class: workflow
topic: "read-suite-summary-before-trailer-and-unmerged-adr-citation"
description: "j38 — a trailer claiming a green run.sh was written before its summary line was read; lint refuses \"agent-fabric ADR-N\" for an ADR not on main"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9e49304b22a61706
---

## j38 — a trailer claiming a green run.sh was written before its summary line was read; lint refuses "agent-fabric ADR-N" for an ADR not on main

Read the last line of `tests/run.sh python` ("all suites passed" vs "N suite(s) FAILED") before
writing a `Supplier-Review:` trailer or pushing; a background wrapper that ends in `tail` exits 0
whatever the suite did, so the task's exit code proves nothing. In j38 (2026-10-17) I committed and
pushed a trailer saying "run.sh python green" on a run that said "2 suite(s) FAILED", and had already
deleted the output; I had to re-run to find the cause and fix it in a further commit.

**Why:** corpus lint (run inside the suite) fails a docstring that cites "agent-fabric ADR-060" while
that ADR is not on origin/main (a Proposed ADR on another branch); two further timing tests
(test_launch_cli, test_control_gzcoord) failed once under load and pass alone and on a re-run.

**How to apply:** `tail -2` the output into the decision, keep the file until the commit is made, write
the bare "ADR-060" inside this repo for an ADR not yet merged, and re-run the whole suite once before
calling a lone timing failure flaky.

*Anchors: `tests/run.sh::suite(s) FAILED`*

*Observed 2026-10-17 (python-dev)*
