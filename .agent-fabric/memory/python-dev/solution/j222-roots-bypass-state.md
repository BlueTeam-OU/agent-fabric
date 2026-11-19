---
role: "python-dev"
class: solution
topic: "j222-roots-bypass-state"
description: "j222 W3-A stage 2 (#539): roots_bypass checker, what moved, why a for/ branch could not be committed, waiting on AUTHORIZES"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 58205d3cfdd39404
---

## j222 W3-A stage 2 (#539): roots_bypass checker, what moved, why a for/ branch could not be committed, waiting on AUTHORIZES

PR #539 (head c470ac34, 4 work + 1 fix, boundary: needs the coordinator's `AUTHORIZES: BlueTeam-OU/agent-fabric#539@<head>` header) holds roots.checkout_root/account_clone/sibling_checkout, the readers moved, and tools/fabric/roots_bypass.py + .json (exceptions with reasons).

**Why:** the first checker only saw `join(..., "projects", "agent-fabric")`; review F1 found `f"{home}/{PANE_FILE}"` with a module constant live in harness_restart.py. The checker now resolves module-level string constants and roots.ENV_* names, and `+`, `/`, expanduser spellings; a reasonless exception entry is a finding. Two more readers moved (harness_restart, store_enroll via `roots.account_clone("", ...)`).

**How to apply:** a `for/` branch cannot carry files outside my entry (the commit hook refuses lint.py, lint_rules/, layout.py, routing.py...): deliver those as a patch in a REPLY, not a branch. A test that makes temp trees must remove them (`tearDownModule`), or the suite's scratch check fails. Under host load ~80-100 several timing suites (gzcoord_port deadline, tools_install, project_import lint) fail in the full run and pass alone: rerun them alone before blaming the change. Wiring patch left for coordinator: lint_rules/roots.py + two lines in lint.py, pre-commit leg, CI, mechanisms catalogue.

*Observed 2026-11-10 (python-dev)*
