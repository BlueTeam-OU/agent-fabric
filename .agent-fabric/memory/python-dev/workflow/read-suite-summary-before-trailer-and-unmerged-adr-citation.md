---
role: "python-dev"
class: workflow
topic: "read-suite-summary-before-trailer-and-unmerged-adr-citation"
description: "j38 claim re-checked 2026-10-20 — the \"N suite(s) FAILED\" last line is still what tests/run.sh ends on, now printed by tests/run.py"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 59f02fd1a251f8f6
  - 9e49304b22a61706
---

## j38 claim re-checked 2026-10-20 — the "N suite(s) FAILED" last line is still what tests/run.sh ends on, now printed by tests/run.py

Read the last line of `tests/run.sh` ("all suites passed" vs "tests/run.sh: N suite(s) FAILED") before
writing a `Supplier-Review:` trailer or pushing; a background wrapper that ends in `tail` exits 0
whatever the suite did, so the task's exit code proves nothing. In j38 (2026-10-17) I committed and
pushed a trailer saying "run.sh python green" on a run that said "2 suite(s) FAILED", and had already
deleted the output; I had to re-run to find the cause and fix it in a further commit.

**Why:** corpus lint (run inside the suite) fails a docstring that cites "agent-fabric ADR-060" while
that ADR is not on origin/main (a Proposed ADR on another branch); timing tests failed once under
load and pass alone and on a re-run. Checked against the tree 2026-10-20: the line is unchanged for a
reader, but `tests/run.sh` is now a forwarder and the text is printed by `tests/run.py` (its
`{PROG}: {failed} suite(s) FAILED`), which is why the old anchor on `tests/run.sh` no longer matched.

**How to apply:** `tail -2` the output into the decision, keep the file until the commit is made, write
the bare "ADR-060" inside this repo for an ADR not yet merged, and re-run the whole suite once before
calling a lone timing failure flaky. A run also waits for the host's full-suite lease when another
agent holds it (a log of one line, "full-suite is held by …"): a background timeout shorter than the wait
kills it before any test ran, so give the run the longest background timeout.

*Anchors: `tests/run.py::suite(s) FAILED`*

*Observed 2026-10-20 (python-dev)*
