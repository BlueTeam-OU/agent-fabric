---
role: "python-dev"
class: solution
topic: "fleetdeck-part2-j97"
description: "j97 #435 merged — FleetDeck harness unit/attach/harness-stop: design choices, assumed herdr-fork JSON shapes, review lessons, what is still unverified live"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9737d27be24fc55b
---

## j97 #435 merged — FleetDeck harness unit/attach/harness-stop: design choices, assumed herdr-fork JSON shapes, review lessons, what is still unverified live

PR BlueTeam-OU/agent-fabric#435 merged 2026-10-31 (head 7958f85f, 7 work, 1 fix, 1 merge; armed on the coordinator's word because a boundary change under 8). The FleetDeck binary is a herdr fork: `--session harness server`, `workspace create --label`, `pane list/run/process-info`, `status server --json`, `terminal attach <terminal_id>`; the JSON shapes were read from the fork's docs, never from a live binary.
Choices: enter-ssh's word `attach` maps to enter's mode `--attach` (moveto.py does lookup + execv), so the root-owned conf fence is reused; the harness pane is the single pane of the workspace labelled `harness`; stop = KillMode=control-group SIGTERM, TimeoutStopSec=100; "pane runs a program" = any foreground pid != shell_pid; five starts in 300 s end the unit in failed.
Review lessons: (1) every value read from the binary's JSON is a shape check with its own message — a missing `label` or `running` is "not understood", never "no pane"/"not running", and ids are full-matched against `[A-Za-z0-9_.:][A-Za-z0-9_.:-]*` before an argv; (2) a root installer chmods only the directories it creates and reads the source's kind from the opened descriptor; (3) a request word like "ensure" trips the brief's rationale lint.
Unverified: everything against the real binary (no zig, no sudo on this account); the live read-back under docs/live-checks/ is still owed and needs the owner's binary. tests/test_launch.py and tests/test_launcher_gateway.py are red on this login even on origin/main (green for the coordinator and in CI) — cause on this login unfound.
**How to apply:** if live JSON differs, fix harness_pane.py and moveto.py harness_terminal together; coordinator's j490 holds the ADR-048 "four words" text and the bootstrap enable --now wait.

*Anchors: `tools/fabric/control/harness_pane.py::ensure`, `runtime/provisioning/moveto/moveto.py::harness_terminal`*

*Observed 2026-10-31 (python-dev)*
