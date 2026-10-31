---
role: "fabric-coordinator"
class: rationale
topic: "cpu-lease-counts-runs-and-threads"
description: "Host load: a lease that counts heavy runs must also cap each run's threads; the cpu slot is exec'd into the tool with build servers off, so a KILL cannot free it under running children"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e53eee6350ccfcdd
---

## Host load: a lease that counts heavy runs must also cap each run's threads; the cpu slot is exec'd into the tool with build servers off, so a KILL cannot free it under running children

On develop-qzapp (10 vCPU) one full agent-fabric suite alone kept load at ~22 on 2026-10-28, with 255 fabric-python processes, because `AGENT_FABRIC_TEST_JOBS` defaults to cpu_count and cargo builds `-j nproc`. A lease that only limits how many runs at once still lets the load multiply. The owner accepted ADR-010 A 2026-10-28 (j412): `cpu` in N=2 slots, each slot giving its child `nproc // N` threads (CARGO_BUILD_JOBS, AGENT_FABRIC_TEST_JOBS, DOTNET_PROCESSOR_COUNT, MAKEFLAGS). Root shims at /usr/local/bin/cargo and /usr/local/bin/dotnet take the slot, because /usr/local/bin comes before /usr/bin. A wrapper that agents must type is opt-in, and a project-side opt-in had covered only gzapp's Makefile.

**Why exec, reversed from the first draft of item 6:** a shim that holds the slot and runs the tool as a child frees the slot when a KILL reaches the shim alone, while the build's children still burn the cores. The shim therefore `exec`s with the slot fd inherited, and the kernel frees the slot only when the last holder exits. The risk is a long-lived inheritor (MSBuild nodes, the MSBuild server, the Roslyn VBCSCompiler). It is switched off with MSBUILDDISABLENODEREUSE=1, DOTNET_CLI_USE_MSBUILD_SERVER=0 and UseSharedCompilation=false, and `fabric-lease cpu --who` marks a slot whose recorded pid is gone `(orphan: a child still runs)`. Built on python-dev-01's for/user/j412-cpu-lease (hold_and_exec in tools/fabric/lease.py).

**How to apply:** for any new lease on a CPU-heavy tool, cap its threads as well. Where a KILL to the top process must not free the resource, exec with the fd inherited, turn off every server that would outlive the run, and make an orphan holder visible. A memory lease is the opposite case: it closes its fd. The dotnet variables' effect still needs a live read-back. Related: [[load-flake-briefs]].

*References: load-flake-briefs*

*Observed 2026-10-28 (fabric-coordinator)*
