---
role: "python-dev"
class: solution
topic: "j114-stale-harness-server-merged"
description: "j114 #480 merged; harness_server_replaced in the session op, counting rule, review/arm/hook traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b2c874efa26234ef
---

## j114 #480 merged; harness_server_replaced in the session op, counting rule, review/arm/hook traps

#480 merged 2026-11-05: `replaced_harness_servers` in tools/fabric/control/ops/identity.py counts the account's own processes whose /proc exe ends " (deleted)" with basename agent-fabric-fleetdeck AND argv[1:4] == --session harness server (the unit's ExecStart). Exe alone also matches `terminal attach` clients and a controller's deck server, which harness-restart does not cure (review F1). Read sits below the faked-`run` guard in `_session`; the test mocks the reader and asserts not called (a real-/proc assertion cannot fail on a clean host).

**Why:** the owner's request: every account ran a deleted binary two days unnoticed.
**How to apply:** TLSv1 warning check = `python3 -W error::DeprecationWarning tests/<file>` (MINIMUM_SUPPORTED is not deprecated). A security-boundary PR (ctl.py, ops/) under 8 work arms only with "the owner's word" in --basis after the owner types "arm N". Hook traps: `env -i ... git commit` is refused by the job-copy guard (lint under env -i, commit bare); `fabric-pr post-review` must be the bare command with `< /literal/path`, report file written with Write. The re-review brief refuses previous_findings on a PR. Full suite at host load ~55 ends test_gzcoord_port and test_launch_cli at 900 s; both pass alone. fabric-jobs switch also wants deliver, the open REPLY, and a memory change.

*Anchors: `tools/fabric/control/ops/identity.py::replaced_harness_servers`*

*Observed 2026-11-05 (python-dev)*
