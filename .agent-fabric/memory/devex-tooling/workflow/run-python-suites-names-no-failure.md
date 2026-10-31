---
role: "devex-tooling"
class: workflow
topic: "run-python-suites-names-no-failure"
description: "tests/run.sh python prints only FAILED_SUITES=<n>, never which suites; find them from the \"== <suite>\" blocks, then compare against the base"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 629be802619487bf
---

## tests/run.sh python prints only FAILED_SUITES=<n>, never which suites; find them from the "== <suite>" blocks, then compare against the base

`tests/run_python_suites.py` counts the suites that exit non-zero (`FAILED_SUITES=<n>`) but does not name them. To find which ones failed, split the log on the `== tests/<suite>.py` headers and look for FAIL, ERROR, Traceback or FAILED inside each block. Then run those suites alone at the base, in a detached worktree under the scratchpad (removed afterwards), and compare their FAIL lines. Seen 2026-10-14 on j122: test_lint (37 cases) and test_assemble (7) failed on the base because of one corpus-lint finding (identities/prompt over its 2500-token budget), and test_roots_readers failed too, as in [[gzcoord-compose-test-login-trap]].

*References: gzcoord-compose-test-login-trap*

*Observed 2026-10-13 (devex-tooling)*
