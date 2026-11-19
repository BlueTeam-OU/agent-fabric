---
role: "fabric-coordinator"
class: solution
topic: "agentd-restart-drill-touch"
description: "how to make the operator's agentd ask to restart mid-command live, without changing code — touch a loaded module under the unit's root, before the command starts"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4045304ebef83b68
---

## how to make the operator's agentd ask to restart mid-command live, without changing code — touch a loaded module under the unit's root, before the command starts

agentd's source watch (`tools/fabric/control/agentd.py` SourceWatcher) compares mtime, size and inode, polls every
`WATCH_POLL_S` (1 s) and waits `QUIET_S` (2 s) for quiet, so `touch` of a loaded module asks for a restart with no
code change. Two traps, both hit on 2026-11-14 (j852):

- Touch under the **unit's** root, `AGENT_FABRIC_ROOT` in `systemctl --user show agent-fabric-agentd -p Environment`
  (the main checkout), never `roots.code_root()` run from a worktree — that resolves to the worktree and the daemon
  never notices.
- Touch **before** starting `fabric-ctl all status` (about 5 s of replies): touched 1–2 s in, the leave lands about 3 s
  later, inside the window where an unheld daemon would leave anyway, so the run proves nothing.

The agentd journal is local time (+01:00); `control-arrivals.jsonl` is UTC. Read-back:
docs/live-checks/2026-11-14-agentd-restart-held-by-ctl-session.md.

*Anchors: `tools/fabric/control/agentd.py::WATCH_POLL_S`, `tools/fabric/control/agentd.py::QUIET_S`, `tools/fabric/control/agentd.py::class SourceWatcher`*

*Observed 2026-11-14 (fabric-coordinator)*
