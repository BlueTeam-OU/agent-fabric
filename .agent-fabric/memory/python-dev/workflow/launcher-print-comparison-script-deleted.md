---
role: "python-dev"
class: workflow
topic: "launcher-print-comparison-script-deleted"
description: "tests/parity/launch_print.py (the --print comparison against the deleted bash launcher) is gone; compare --print output by running the launcher with its fake ori and claude as tests/test_launch_cli.py does"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 31011f2c7523223c
  - 5d9477fc4b81c4f2
---

## tests/parity/launch_print.py (the --print comparison against the deleted bash launcher) is gone; compare --print output by running the launcher with its fake ori and claude as tests/test_launch_cli.py does

The wave-4 `--print` comparison script and its recorded output were deleted in the test-suite audit (PR #203), because the bash launcher it compared against no longer exists. To read what `--print` prints for a role and provider, run `runtime/openrouter/launch --print` (with AGENT_FABRIC_ALLOW_STALE=1 from a worktree that is behind origin/main), or in the sandbox tests/test_launch_cli.py builds (a fixture fabric with a fake `ori` and `claude` on PATH). Checked 2026-10-20: the live `--print` runs and its output was the same before and after j72's changes.

**Why:** the comparison had nothing left to compare against.
**How to apply:** do not point a reader at a deleted script; `--help` passes through to claude, so read usage from `tools/fabric/launch.py`'s docstring.

*Anchors: `tools/fabric/launch.py::launch`, `tests/test_launch_cli.py`*

*Observed 2026-10-20 (python-dev)*
