---
role: "fabric-coordinator"
class: solution
topic: "stripped-run-drops-check-detail"
description: "a stripped-nightly FAIL shows no values — tests/stripped_run.py keeps only FAIL/Error lines"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8bd44c961902f97a
---

## a stripped-nightly FAIL shows no values — tests/stripped_run.py keeps only FAIL/Error lines

tests/stripped_run.py:230 prints only lines of a failing file that contain
"FAIL" or "Error", so a check's indented detail line (the compared values)
never reaches the CI log. Diagnosing a stripped-nightly red from the log
alone is guessing; reproduce on the runner (workflow_dispatch) or get the
filter widened. Found on j627 (2026-11-05): the flaky birth-time check in
tests/test_store_enroll_cli.py:161 failed 4 of ~20 runs, passed 15/15
locally; contracted to python-dev-02 (REQUEST 01a1ad01-832e-70c8-b99a-0f4a91790698).
Resolved: #495 made stripped_run keep detail lines; the values showed CI's
`date +%3N` misreads a stamp fraction beginning with 0 (1 run in 10), the
id was right. #496 gave the j567 cases a fixture registry. Nightly on main
green 2026-11-05 (run 42118034345). Lesson: a flake that passes 15/15
locally is the runner's tooling until its values are seen.
See [[tests-and-suite]].

*References: tests-and-suite*

*Anchors: `tests/stripped_run.py::if "FAIL" in ln or "Error" in ln`*

*Observed 2026-11-05 (fabric-coordinator)*
