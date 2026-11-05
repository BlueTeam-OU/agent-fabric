---
role: "fabric-coordinator"
class: solution
topic: "worktree-reads-main-checkout-approval"
description: "In a linked git worktree Claude Code (2.1.286 and 2.1.311, claude -p) reads hasClaudeMdExternalIncludesApproved from the main checkout's ~/.claude.json entry, never the worktree's own path"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5c2d09fcbfdba3aa
  - 689e7e434a9f44f4
---

## In a linked git worktree Claude Code (2.1.286 and 2.1.311, claude -p) reads hasClaudeMdExternalIncludesApproved from the main checkout's ~/.claude.json entry, never the worktree's own path

Measured 2026-10-20 on 2.1.286 (j174, #332) and again on 2.1.311 on 2026-11-03 (j560,
docs/live-checks/2026-11-03-claude-code-2-1-311-readback.md R1). The fixture was a scratch projects/ with the
workspace CLAUDE.md, a repository and a linked worktree beside it; on 2.1.311 each case had a scratch HOME and
the worktree was an orphan. `claude -p` in the worktree loaded agent-fabric/CLAUDE.md only when the MAIN
checkout's entry carried the approval, and the worktree's own entry was ignored either way. Claude Code wrote
nothing to either entry. So workspace_trust.py approving each registered checkout covers its worktrees, and an
approval missing on a checkout disables the fabric's rules in every worktree of it. Not measured: the trust key
in a worktree, an interactive session's dialog, and a main checkout at an unrelated or symlinked path.

**How to apply:** fix a missing approval on the checkout (bootstrap's trust step), never on a worktree; read
this back when the pin moves. Related: [[worktree-reads-main-checkout-approval]].

*References: worktree-reads-main-checkout-approval*

*Anchors: `tools/fabric/workspace_trust.py::hasClaudeMdExternalIncludesApproved`*

*Observed 2026-11-03 (fabric-coordinator)*
