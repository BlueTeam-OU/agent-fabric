---
role: "devex-tooling"
class: solution
topic: "narrowed-path-suite-needs-fabric-root"
description: "a gzapp suite that runs a fabric hand-over on a narrowed PATH must resolve and export AGENT_FABRIC_ROOT first, or a local CI-env run differs from CI"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 709af7d3377bd069
---

## a gzapp suite that runs a fabric hand-over on a narrowed PATH must resolve and export AGENT_FABRIC_ROOT first, or a local CI-env run differs from CI

gzapp's hand-over scripts find agent-fabric through `gzapp_fabric_root`
(tools/gh/fabric-root.sh): AGENT_FABRIC_ROOT if set, else `git rev-parse`.
CI exports AGENT_FABRIC_ROOT through $GITHUB_ENV (_ban-checks.yml), so CI
never asks git; a local run with AGENT_FABRIC_* stripped does. A suite case
whose PATH has no git then trips run_suite's exported
command_not_found_handle (it records the call even under `2>/dev/null`),
and from a worktree not beside agent-fabric the fallback root is wrong.
Rule: a suite resolves `AGENT_FABRIC_ROOT="$(gzapp_fabric_root "$SCRIPT_DIR")"`
and exports it before any narrowed-PATH case, as
test_scan_semantic_collisions.sh does. Fixed for test_check_workflows_lint.sh
in gzapp b980fe719 (develop-qzapp/devex-tooling/fix/tooling-batch-3, j110).

*Observed 2026-10-13 (devex-tooling)*
