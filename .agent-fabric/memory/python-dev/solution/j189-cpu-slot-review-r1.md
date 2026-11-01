---
role: "python-dev"
class: solution
topic: "j189-cpu-slot-review-r1"
description: "j189 (#425 F1/F4/F2) lease.py cpu slots: regular_only open, skip-unusable semantics, a hang is a mutation result, rm of test sandbox needs chmod"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 54ac2e9c1de1c1c0
---

## j189 (#425 F1/F4/F2) lease.py cpu slots: regular_only open, skip-unusable semantics, a hang is a mutation result, rm of test sandbox needs chmod

j189 delivered `for/user/j412-review-r1` head a8ebd9f5 (F1 `06b3d24a`, F4 `8bdf4f62`, F2 `a8ebd9f5`).

- `lease.open_lease(path, regular_only=True)` is the cpu-slot opener: O_NONBLOCK plus fstat S_ISREG, OSError(EINVAL, "not a regular file") otherwise. Other leases and tests/run.py keep the blocking open.
- An unusable slot is skipped with one stderr line (once per slot per call); exit 2 `reason=unopenable` only when every slot is unusable, in `acquire_cpu` and `who_cpu`.
- `cpu_child_env` keeps min(existing, J) for CARGO_BUILD_JOBS/DOTNET_PROCESSOR_COUNT; the digit string is length-capped before int().

**Why:** a FIFO planted as a lease file blocks plain open() forever, so a mutation that removes the guard shows as a hang with no FAIL line; run such a mutation under `timeout` and read "no OK line" as the failure.

**How to apply:** a killed test run leaves a read-only sandbox (the shim installer's prefix) in the scratchpad: `chmod -R u+w` before `rm -rf`. A hook refuses `lint | tail && git commit`: lint to a log, read rc, then commit. Also see [[bounded-subprocess-three-seams]].

*References: bounded-subprocess-three-seams*

*Anchors: `tools/fabric/lease.py::open_lease`, `tools/fabric/lease.py::cpu_child_env`, `tools/fabric/lease.py::acquire_cpu`*

*Observed 2026-10-30 (python-dev)*
