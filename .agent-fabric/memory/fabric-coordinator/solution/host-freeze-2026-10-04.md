---
role: "fabric-coordinator"
class: solution
topic: "host-freeze-2026-10-04"
description: A silent journald plus no OOM line means memory exhaustion into zram thrash; oomd and 10G/12G caps applied; agentd samples memory pressure
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8f8b18b0c6b5c7bc
  - e2cc8b436b047df6
---

## A silent journald plus no OOM line means memory exhaustion into zram thrash; oomd and 10G/12G caps applied; agentd samples memory pressure

A host freeze with a silent journal and no OOM or hung-task line was memory exhaustion sliding into zram thrash (develop-qzapp, 2026-10-04; a heavy rustc load beside 18 sessions). Not fully provable, since nothing was logged.

The owner applied, as root: `systemctl enable --now systemd-oomd`; `/etc/systemd/system/user-.slice.d/50-agent-fabric-memory.conf` (MemoryHigh=10G, MemoryMax=12G, ManagedOOMMemoryPressure=kill); `/etc/systemd/system/-.slice.d/50-agent-fabric-swap.conf` (ManagedOOMSwap=kill). These are host state, not in the tree.

**Diagnosing a later freeze** without root: `journalctl -b -1` shows only your own user journal. Ask the owner for `sudo journalctl -b -1 -o short-monotonic`; a wall-clock gap whose monotonic time also jumps means the qube ran and did not log.

**Data for a post-mortem:** the control agent samples `/proc/pressure/memory` and free memory every minute into a ring in its state dir (runtime/control/pressure.mjs, tools/fabric/control/pressure.py, the `memory_pressure` host op); `fabric-ctl host` prints it as the `memory:` line.

Heavy builds under a capped `fabric-lease heavy-build` is an intention only: no lease name or rule in the tree names it.

*Observed 2026-10-10 (fabric-coordinator)*
