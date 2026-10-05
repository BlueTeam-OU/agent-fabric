---
role: "python-dev"
class: solution
topic: "gzcoord-tests-reach-the-host-workspace"
description: "GZCoord command tests read the real projects/.gzcoord unless AGENT_FABRIC_ROOT points at a scratch workspace; green on a non-hosting account proves nothing"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fdf5fd018dbe4b8a
---

## GZCoord command tests read the real projects/.gzcoord unless AGENT_FABRIC_ROOT points at a scratch workspace; green on a non-hosting account proves nothing

inbox.workspace() is the parent of AGENT_FABRIC_ROOT (or of the checkout). ensure_relay reads <workspace>/.gzcoord/venv/bin/claude-bridge. On an account that hosts the relay (the coordinator's), a command test that left the root alone asked the REAL relay's /status, and would have started it were it down. My account hosts nothing, so the suite was green here and failed there (#93 round 3).
**Why:** a test leans on machine state its author's account lacks.
**How to apply:** give every command test a scratch workspace: AGENT_FABRIC_ROOT=<scratch>/agent-fabric, a symlink to the checkout (test_gzcoord_protocol.cmd_env does it). Pin it with a case that asks the env for its relay runtime dir. Prove it by running from a scratch clone whose parent holds a planted .gzcoord/venv/bin/claude-bridge, with the old head as the control.

*Observed 2026-10-04 (python-dev)*
