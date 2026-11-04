---
role: "python-dev"
class: workflow
topic: "stale-agent-fabric-root-worktree-breaks-fabric-commands"
description: "A session launched in a stale job worktree runs fabric commands from it (AGENT_FABRIC_ROOT); after a schema or module change they exit 6 or crash — prefix them with the main checkout's root"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 86c8214e5d3eedd6
---

## A session launched in a stale job worktree runs fabric commands from it (AGENT_FABRIC_ROOT); after a schema or module change they exit 6 or crash — prefix them with the main checkout's root

A session started inside an old job worktree has AGENT_FABRIC_ROOT pointing at it, so `gzcoord-inbox`, `gzcoord-send` and `fabric-jobs` load that tree's code. When origin/main moves on (episodic journal schema 2 to 3, `fabric_identity.hold_path`), the watch exits 6 ("schema version 3, newer than this code's 2"), send refuses ("not sent: a message is kept before it leaves"), and `fabric-jobs switch` dies with AttributeError.

**Why:** 2026-10-30, j75. The "update the fabric" advice was already done; the stale tree was the session's own root. `git merge` in that worktree is blocked by the job-ended hook once the job left active.

**How to apply:** run the command as `AGENT_FABRIC_ROOT=~/projects/agent-fabric <command>` (the main checkout, kept on main). Do not use GZCOORD_JOURNAL=off: it sends without the journal. Related: [[job-worktree-needs-fabric-jobs-project-and-enterworktree]].

*References: job-worktree-needs-fabric-jobs-project-and-enterworktree*

*Anchors: `tools/fabric/episodic.py::SCHEMA_VERSION`, `tools/fabric/hold_view.py::hold_path`*

*Observed 2026-10-31 (python-dev)*
