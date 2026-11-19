---
role: "fabric-coordinator"
class: workflow
topic: "carrier-restart-time-wait"
description: "Fleet carrier restart (interweave-stop then -start per account): a start right after a stop can be refused for a TIME_WAIT on the daemon's port; retry after ~20 s. Read the carrier's process start time before assuming it runs old code"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e52cf1c9c97b1ea2
---

## Fleet carrier restart (interweave-stop then -start per account): a start right after a stop can be refused for a TIME_WAIT on the daemon's port; retry after ~20 s. Read the carrier's process start time before assuming it runs old code

2026-11-09 (j603), restarting every account's interweave-client@gzcoord one at a time:
- `fabric-ctl flutter-dev-01 interweave-start` right after its stop was refused: "local port 47111
  is in use by a TIME_WAIT connection of uid 0 … nothing was started". Nothing is wrong; the
  socket clears in under a minute. Retry the start every ~20 s until it binds.
- Read-back per account without reading its home: `fabric-ctl <a> interweave` (status ok, channel
  ok) plus `ps -u <a> -o lstart=,args= | grep '[g]zcoord-carrier run'`: exactly one process,
  started after the stop. Reading another account's /proc fds or ~/.local is refused by auto mode;
  your own carrier's `/proc/<pid>/fd` shows `interweave/deliveries.lock` (#476 F01) when live.
- The job's premise ("running since 10-31 on old code") was stale: a host reboot on 2026-11-07
  12:08 had restarted every carrier on the fleet's code then (already past #476). Before a
  "restart to pick up code" job, compare `ps lstart` with the merge time and
  `git log <code-at-start>..origin/main -- tools/fabric/gzcoord/carrier`; this time #509's
  carrier changes were still the reason to restart.

*Anchors: `tools/fabric/gzcoord/carrier/record.py::deliveries.lock`*

*Observed 2026-11-09 (fabric-coordinator)*
