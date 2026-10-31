---
role: "fabric-coordinator"
class: workflow
topic: "console-session-not-launched"
description: "a coordinator session the owner starts with plain `claude` has no launch profile; fabric-fresh refuses, so every job handoff falls to the owner"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 85e5f95ba5fd3a46
---

## a coordinator session the owner starts with plain `claude` has no launch profile; fabric-fresh refuses, so every job handoff falls to the owner

fabric-fresh refuses when AGENT_FABRIC_LAUNCH_PROFILE is unset ("this session
was not started by the launcher … use /clear"). On 2026-10-24 my console
session was a plain `claude`, so j381/j388 and j392 twice came back to the
owner as "sessions only you can open". The owner: that should not happen.

**Why:** the one-job guard judges the session's directory, and only a
launcher-started session can be relaunched into a job's worktree.

**How to apply:** at session start check `env | grep AGENT_FABRIC_LAUNCH_PROFILE`.
If empty, say so at once and ask the owner to relaunch my login through the
launcher, before any job needs another working copy, never at hand-off time.
With it set, run `fabric-fresh --job <id>` myself. Related: [[job-in-other-repo-needs-fresh-session]].

*References: job-in-other-repo-needs-fresh-session*

*Anchors: `tools/fabric/fresh.py::launch_refusal`*

*Observed 2026-10-25 (fabric-coordinator)*
