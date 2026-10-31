---
role: "fabric-coordinator"
class: workflow
topic: "resumed-subagent-loses-worktree"
description: "A writing subagent resumed by SendMessage runs in the session clone, not its worktree: dispatch a new isolated agent for each writing step"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - dc20d630e48f03d3
---

## A writing subagent resumed by SendMessage runs in the session clone, not its worktree: dispatch a new isolated agent for each writing step

Measured 2026-10-18 (j228): a code-low agent dispatched with `isolation: worktree` reported
`<clone>/.claude/worktrees/agent-<id>` as its cwd; resumed with SendMessage after it finished, it reported the
session clone itself, on the session's branch (`main`), and its worktree and branch were gone (it had changed
nothing, so the harness had cleaned them). The clone guard then fences it read-only, correctly.
Not observed: a resumed agent whose worktree held changes.

**Why:** a resumed writing agent writes, or tries to, in the session's own checkout.

**How to apply:** never resume a writing agent for more work; dispatch a fresh one with isolation worktree.
SendMessage is fine for read-only follow-ups. The guard's refusal now says so (commit b8b29ecf).
The SSH half of j228 (SSH_AUTH_SOCK empty in a worktree subagent) was not probed: auto mode refused reading it as
credential exploration; it is the owner's to decide.

*Anchors: `runtime/claude-code/hooks/subagent-clone-guard.sh::its isolation is not restored`*

*Observed 2026-10-18 (fabric-coordinator)*
