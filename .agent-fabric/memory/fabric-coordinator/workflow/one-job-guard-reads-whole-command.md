---
role: "fabric-coordinator"
class: workflow
topic: "one-job-guard-reads-whole-command"
description: "the one-job guard refuses a commit or fabric-pr arm in the job's own copy when the same Bash command also names another working copy, even only to read it"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e6bc37bd69b9ca5f
---

## the one-job guard refuses a commit or fabric-pr arm in the job's own copy when the same Bash command also names another working copy, even only to read it

On 2026-11-05 (j499, gzapi.brand#14) the one-job guard (ADR-037 rule 3)
refused two commands that committed or armed in the job's own working copy,
because each also named `~/projects/agent-fabric`. The first was a
`git commit` followed by `git -C ~/projects/agent-fabric worktree add`. The
second was a read-only `git -C ~/projects/agent-fabric show` followed by
`fabric-pr arm --dry-run`. The guard attributes the commit or publish verb
to every path the command string names, not only to the directory the verb
runs in.

**How to apply:** put a read of another working copy in a separate Bash call
from any `git commit`, `git push` or `fabric-pr` call. To read the fabric
at a pinned commit, use a scratchpad worktree path rather than
`~/projects/agent-fabric`. Related: [[job-in-other-repo-needs-fresh-session]].

*References: job-in-other-repo-needs-fresh-session*

*Anchors: `agent-fabric:runtime/claude-code/hooks/job-copy-guard.py::one job's working copy`*

*Observed 2026-11-05 (fabric-coordinator)*
