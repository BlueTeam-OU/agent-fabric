---
role: "python-dev"
class: workflow
topic: "text-scan-tests-read-your-new-tests"
description: "a new test containing a literal another suite scans for (test_branches_sweep's double-quoted sweep flag) turned platform-smoke red while my queued full suite had not run; run the scanning neighbours before pushing"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fb1206fb442fdfc6
---

## a new test containing a literal another suite scans for (test_branches_sweep's double-quoted sweep flag) turned platform-smoke red while my queued full suite had not run; run the scanning neighbours before pushing

PR #355 (j149): my Help cases in tests/test_control_ctl.py named the sweep flag in double quotes, and
tests/test_branches_sweep.py's `test_every_suite_that_runs_a_sweep_names_a_configuration_directory_of_its_own`
reads every tests/*.py as TEXT: a file with that literal and no `claude-config` is "a suite that runs a sweep". It
failed twice (my first commit, then again when the F3 fix re-added the literal in a hand-written list) and went red on
both platform-smoke runs. Locally the full suite was queued behind another login's full-suite lease for over two
hours, so the scan never ran before I pushed.

**Why:** the text-scanning tests (facade-split-monkeypatch-trap) judge a file by what it spells, not by what it does.
**How to apply:** before pushing a test change, run the suites that scan tests (`grep -ln "os.listdir.*tests" tests/*.py`),
or at least test_branches_sweep, directly under `env -i`; do not wait for the full suite. Derive a flag list from the
parser's source (`inspect.getsource` + regex) rather than spelling it. `tests/run.sh` waits up to 2 h for the lease
and reads the tree when it starts, so an edit while it waits is covered by that run (see [[never-edit-while-the-suite-runs]]).

*References: never-edit-while-the-suite-runs*

*Anchors: `tests/test_branches_sweep.py::claude-config`, `tests/test_branches_sweep.py::test_every_suite_that_runs_a_sweep_names_a_configuration_directory_of_its_own`*

*Observed 2026-10-22 (python-dev)*
