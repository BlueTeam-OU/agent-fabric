---
role: "fabric-coordinator"
class: workflow
topic: "suite-verdict-not-pipeline-exit"
description: "A suite run piped into tail/grep reports the pipe's exit, not the suite's: read the suite's own verdict line (FAILED_SUITES=, N suite(s) FAILED) before saying it passed"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 45b256dde5127854
---

## A suite run piped into tail/grep reports the pipe's exit, not the suite's: read the suite's own verdict line (FAILED_SUITES=, N suite(s) FAILED) before saying it passed

`tests/run.sh python | tail -3; echo exit=$?` prints the exit of `tail`, which is 0 whatever the suite did. On
2026-09-17 language-culture-ge reported "tests/run.sh passed, exit 0" and corrected itself the same hour: the suite
said 2 FAILED (its REPLY 01a0b17e-0b98-7234-9107-0a9db009aa09). The same shape recurs in this session's own
commands: every background run here pipes the suite into grep or tail.

**Why:** a verdict taken from the wrong process is a false pass, and a pass is what arms a PR.

**How to apply:** judge a run by the suite's own last lines — `FAILED_SUITES=<n>` for the python section,
`tests/run.sh: N suite(s) FAILED` or `all suites passed` for the whole — or by `${PIPESTATUS[0]}`, never by `$?`
after a pipe. Say which line the verdict came from. Related: [[fold-then-full-suite]].

*References: fold-then-full-suite*

*Anchors: `tests/run_python_suites.py::FAILED_SUITES`*

*Observed 2026-10-18 (fabric-coordinator)*
