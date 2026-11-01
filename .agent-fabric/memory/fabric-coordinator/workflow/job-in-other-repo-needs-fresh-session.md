---
role: "fabric-coordinator"
class: workflow
topic: "job-in-other-repo-needs-fresh-session"
description: "a session launched in agent-fabric cannot commit for a job in another repository; the one-job guard judges the session cwd, which the harness resets"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0560dba4df7f30d8
---

## a session launched in agent-fabric cannot commit for a job in another repository; the one-job guard judges the session cwd, which the harness resets

The one-job guard (#348, ADR-037 rule 3) judges a `git commit` by the session's
directory. The harness resets the shell to the launch directory after every
command, so neither `cd X &&` nor `git -C X` gets a commit past it (2026-10-21,
j265 in InterWeave from a session started in agent-fabric). The route is
`fabric-fresh --job <id>`: the launcher starts the next session in the job's
working copy. Check the job's `project`/`working_copy` when it is added: j265
was filed under agent-fabric by default and its switch made an empty
agent-fabric worktree. A self-added job for another repository takes
`--project` and `--working-copy`.

A misfiled job cannot be retargeted: `fabric-jobs` has no edit verb. Re-add
it with `--project`/`--working-copy` (high priority), drop the old one naming
the new id, then `fabric-jobs switch <new>` (2026-10-24: j356 → j370, the
second time a self-added InterWeave job landed under agent-fabric). The guard
also refuses `fabric-pr arm --dry-run` in another copy, not only commits.

The same holds for a supply that belongs to another of my jobs, even in the
same repository: on 2026-10-30, during j412, a `git worktree add … && git
cherry-pick` into the scratchpad for j457's supply was refused whole (nothing
was created). The route: tell the waiting agent where the commit already sits,
so it can write against it now, and give the other job its next step with
`fabric-jobs block <id> --on <its cleared request> "NEXT: …"`. Free text alone
blocks the job with a warning and never clears by itself; a checkable blocker that has already cleared keeps the job
eligible at the next switch while still carrying the note.

*Anchors: `tools/fabric/fresh.py::--job`*

*Observed 2026-10-30 (fabric-coordinator)*
