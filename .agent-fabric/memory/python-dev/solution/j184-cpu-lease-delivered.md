---
role: "python-dev"
class: solution
topic: "j184-cpu-lease-delivered"
description: "cpu lease (j184) shape and its two fixture-guard traps; exec-with-inherited-fd, installer, roots seam"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f572b20b95a18cfe
---

## cpu lease (j184) shape and its two fixture-guard traps; exec-with-inherited-fd, installer, roots seam

cpu lease delivered on for/user/j412-cpu-lease (25962750): lease.py slots cpu.1..N, tools/fabric/cpu_shim.py, provisioning/install_cpu_shims.py (hash-named copy + bash forwarders), tests/test_cpu_lease.py.

The coordinator reversed item 2 mid-job: the shim EXECS the tool with the slot fd inheritable (a leftover child keeps the slot; --who says orphan); no child/signal forwarding, so `fabric-lease cpu -- cmd` is a usage error.

**Why:** a KILL to a wrapper must not free the slot under a running build.
**How to apply:** traps found: tools/ modules must not hand-join `policies/` (test_roots_seam: use roots.policy); a test that runs a tool with AGENT_FABRIC_ROOT=HERE or reads a live policies/ file fails test_own_instance_tree and test_tests_read_fixtures (use tests/instance_fixtures own_instance_tree + a fixture tree). Run those guards before delivering a test touching instance paths. A `pkill -f` pattern is blocked by the hook; a mutation list needs patterns that occur once.

*Observed 2026-10-28 (python-dev)*
