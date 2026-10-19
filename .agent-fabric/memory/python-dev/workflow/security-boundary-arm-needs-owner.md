---
role: "python-dev"
class: workflow
topic: "security-boundary-arm-needs-owner"
description: "a PR touching tools/fabric/control/ctl.py is a security-boundary change; under 8 work commits it arms only on the owner's word"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 81d8d2aa462c6f7b
---

## a PR touching tools/fabric/control/ctl.py is a security-boundary change; under 8 work commits it arms only on the owner's word

#272 (j39, 2026-10-15) changed tools/fabric/control/ctl.py; `fabric-pr arm --dry-run --basis x` refused: "security-boundary change under 8 arms only on the owner's word", or an architect-cto REPLY carrying `AUTHORIZES: <repo>#<n>@<sha>` given as `--authorization <id>`. Plain `arm --dry-run` without `--basis` only says the basis is required, hiding this. The owner's "merge 272" was the word; basis quoted it.

**Why:** projects/agent-fabric/integration/gh/arm.json lists the boundary paths; the coordinator cannot arm another session's PR.

**How to apply:** when a change touches control/ code, plan for the owner's word at 3 work commits; run `arm --dry-run --basis "dry run"` early. Also: a Node-parity frozen test (tests/test_control_frozen.py) needs a cut for any new table text; the all-tables case hashes the table, so its fixture py body must cut too. See [[ci-env-for-lint-and-mutations]].

*References: ci-env-for-lint-and-mutations*

*Observed 2026-10-15 (python-dev)*
