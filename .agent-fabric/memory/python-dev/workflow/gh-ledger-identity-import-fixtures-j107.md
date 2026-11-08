---
role: "python-dev"
class: workflow
topic: "gh-ledger-identity-import-fixtures-j107"
description: A module that gains an import of runtime/identity breaks every test fixture tree that copies it; and a background tests/run.sh needs the 2h limit because it can queue for the lease
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 68f9a7297b5344f8
---

## A module that gains an import of runtime/identity breaks every test fixture tree that copies it; and a background tests/run.sh needs the 2h limit because it can queue for the lease

gh_ledger.py imports `identity` (runtime/), so every test fixture that copies gh.py/gh_ledger.py into a fake tree needs `runtime/identity.py` too: test_new_agent_cli, test_repo_settings_cli and test_statusline_cli failed in the full run and in CI platform-smoke while the suites I had edited were green. Grep the module's name under tests/ before pushing an import change and run the full tests/run.sh, not only the edited suites.

`tests/run.sh` can wait up to 2h for the host full-suite lease: run it in the background with timeout 7200000, not 1800000 (a 30-minute run was killed while still waiting).

**Why:** two red full runs and a red CI before green. **How to apply:** when a shared module gains an import, list its fixture copies first.

*Anchors: `tools/fabric/gh_ledger.py::import identity`, `tests/test_new_agent_cli.py::runtime/identity.py`*

*Observed 2026-11-02 (python-dev)*
