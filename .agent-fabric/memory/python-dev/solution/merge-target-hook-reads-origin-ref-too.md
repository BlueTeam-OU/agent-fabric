---
role: "python-dev"
class: solution
topic: "merge-target-hook-reads-origin-ref-too"
description: "memory-write-check judged merge_target from the working tree only; a checkout behind origin/main warned falsely"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 27d0304bb7c308f6
---

## memory-write-check judged merge_target from the working tree only; a checkout behind origin/main warned falsely

j109: `unresolved_merge_target` now also reads the slice directory from the local
`origin/HEAD`/`origin/main` ref (`committed_headings`, no fetch) and warns only when neither
tree holds the heading. Delivered on `for/user/memory-write-check-merge-target-remote`.

**Why:** the drain reads the remote's corpus; a job worktree cut from older main lacks headings
that exist there. Fixture traps: `other_project_cases` rewrites the operator registry at the same
path, so a later case must register its project in an operator dir of its own; a fixture without
a fetched `origin/main` ref cannot show the bug.

**How to apply:** a stale local origin ref still warns falsely (the hook must not fetch). A
whole-suite run alongside other work timed out `test_gzcoord_port` `--deadline`; it passes alone.

*Anchors: `runtime/claude-code/hooks/memory-write-check.py::committed_headings`*

*Observed 2026-11-11 (python-dev)*
