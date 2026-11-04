---
role: "fabric-coordinator"
class: solution
topic: "worktree-reads-main-checkout-approval"
description: "In a linked git worktree Claude Code (2.1.286, claude -p) reads hasClaudeMdExternalIncludesApproved from the main checkout's ~/.claude.json entry, never the worktree's own path"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 689e7e434a9f44f4
---

## In a linked git worktree Claude Code (2.1.286, claude -p) reads hasClaudeMdExternalIncludesApproved from the main checkout's ~/.claude.json entry, never the worktree's own path

Measured 2026-10-20 (j174, #332): a scratch projects/ with the workspace CLAUDE.md, a repo and a
linked worktree beside it; claude -p in the worktree loaded agent-fabric/CLAUDE.md only when the
MAIN checkout's entry carried the approval; the worktree's own entry was ignored either way. So
workspace_trust.py approving each registered checkout covers its worktrees, and an approval absent
on a checkout disables the fabric's rules in its worktrees. Not measured: the trust key
(hasTrustDialogAccepted) in a worktree, an interactive session, a worktree whose checkout sits at
an unrelated or symlinked path. The record is docs/live-checks/2026-10-20-worktree-include-approval.md.

*Anchors: `docs/live-checks/2026-10-20-worktree-include-approval.md::main checkout`*

*Observed 2026-10-20 (fabric-coordinator)*
