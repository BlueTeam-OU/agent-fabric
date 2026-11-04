---
role: "python-dev"
class: solution
topic: "j191-lease-f5-unusable-count"
description: "When a docstring lists per-variable rules, check each code branch — cpu_child_env's TEST_JOBS_ENV keeps junk and 0 where the cargo/dotnet bounds replace them; and the wait line must count unusable slots"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - cad4e28c3a16978a
---

## When a docstring lists per-variable rules, check each code branch — cpu_child_env's TEST_JOBS_ENV keeps junk and 0 where the cargo/dotnet bounds replace them; and the wait line must count unusable slots

`acquire_cpu` prints "N/M held, K unusable: ..." in the wait line and both 75 refusals, because an unusable slot is never free to the caller and "1/2 held" alone reads as a slot to wait for. Test: cpu.1 mode 000 + cpu.2 held; dropping the count fails 3 checks in tests/test_cpu_lease.py.

**Why:** the first docstring rewrite described `AGENT_FABRIC_TEST_JOBS` as "like the others, except a higher number is lowered with a line"; the code keeps a non-number or 0 there, where CARGO_BUILD_JOBS becomes the slot's jobs (review of #429, F3).
**How to apply:** check a docstring against every branch of the code it describes, not the first. A suite wait loop on `grep '^exit '` matched a test line "exit codes"; match `^exit [0-9]+$`.

*Anchors: `tools/fabric/lease.py::cpu_child_env`, `tools/fabric/lease.py::acquire_cpu`*

*Observed 2026-10-30 (python-dev)*
