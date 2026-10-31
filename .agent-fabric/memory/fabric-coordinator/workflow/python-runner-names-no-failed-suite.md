---
role: "fabric-coordinator"
class: workflow
topic: "python-runner-names-no-failed-suite"
description: "tests/run.sh says FAILED_SUITES=1 but never names the suite; find it by the '== tests/<file>' block whose last line is not an OK/passed verdict"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 11c2eeb6f8e2d147
---

## tests/run.sh says FAILED_SUITES=1 but never names the suite; find it by the '== tests/<file>' block whose last line is not an OK/passed verdict

tests/run_python_suites.py prints each suite's output under `== tests/<file>.py` and only a count at the end
(`FAILED_SUITES=<n>`); no line names the failing file, and grepping for FAIL hits fixture output (test_shim's
"FAIL: acme/…", test_stripped_run's "tests/test_reads_live.py: FAILED"), not real failures. On 2026-10-28 (j448
supply 12424efe) the red one was tests/test_run.py, a /proc/<pid>/stat FileNotFoundError at load 15, green alone.
Find it with a short script: split the output on `\n== (tests/...py)\n` and print each block whose last line is not
an OK / passed / "all passed" verdict. Corpus lint was the other red, and exits 1 on a clean main checkout too
(another project's INDEX drift): compare against main before calling it yours. Related: [[suite-verdict-not-pipeline-exit]], [[load-flake-briefs]].

*References: load-flake-briefs, suite-verdict-not-pipeline-exit*

*Anchors: `tests/run_python_suites.py::FAILED_SUITES=`*

*Observed 2026-10-28 (fabric-coordinator)*
