---
role: "python-dev"
class: workflow
topic: "launcher-print-comparison-script-deleted"
description: "tests/parity/launch_print.py (the --print comparison against the deleted bash launcher) is gone; compare --print output by running the launcher with its fake ori and claude as tests/test_launch_cli.py does"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 31011f2c7523223c
---

## tests/parity/launch_print.py (the --print comparison against the deleted bash launcher) is gone; compare --print output by running the launcher with its fake ori and claude as tests/test_launch_cli.py does

The slice's pointer to `tests/parity/launch_print.py` is stale: the script and its recorded wave-4 output were deleted in the test-suite audit
(PR #203), because the bash launcher it compared against no longer exists. To read what `--print` prints for a role and provider, run
`runtime/openrouter/launch --print` in the sandbox `tests/test_launch_cli.py` builds (a fixture fabric with a fake `ori` and `claude` on PATH),
or run the launcher itself.

**Why:** the comparison had nothing left to compare against.
**How to apply:** do not point a reader at the deleted script; the rest of the slice (`--help` passes through to claude, so read usage from
`tools/fabric/launch.py`'s docstring) still holds.

*Observed 2026-10-11 (python-dev)*
