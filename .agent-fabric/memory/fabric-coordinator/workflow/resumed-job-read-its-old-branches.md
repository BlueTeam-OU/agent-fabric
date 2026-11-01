---
role: "fabric-coordinator"
class: workflow
topic: "resumed-job-read-its-old-branches"
description: "Resuming a job: list every local branch with its job number (git branch --list '*j<N>*') before drafting; an earlier session's draft may sit on a branch the switch did not name"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 92c281f9dbffa5b6
---

## Resuming a job: list every local branch with its job number (git branch --list '*j<N>*') before drafting; an earlier session's draft may sit on a branch the switch did not name

In j412 (2026-10-28) the switch named the branch `feat/j412-owner-2026-10-26-host-at`, which was empty. A 333-line design draft by an earlier session sat on `feat/j412-heavy-job-lease-draft` (1e44e873). I drafted from scratch, got the owner's acceptance, and sent the REQUEST before `fabric-jobs switch` listed the old branch. The old draft held the slot through exec (a KILL cannot free it under a running build). Mine had dropped that, so the contract had to be corrected after it was sent (REPLY 01a181cb). Starting a different job in the same session then made the job guard refuse every further commit.

**Why:** the job note and the switch's branch name do not list every artifact a job has. Every branch carrying the job number may hold one.

**How to apply:** at the start of a resumed job, run `git branch -a --list '*j<N>*'` and `git log origin/main..<each>`, and read what is there before writing anything. Never `fabric-jobs start` a second job in the same session to finish the first: block the first with the pending edit at the front of its note. Related: [[readded-job-check-tree-first]], [[job-branch-via-switch]].

*References: job-branch-via-switch, readded-job-check-tree-first*

*Anchors: `tools/fabric/jobs.py::switch`*

*Observed 2026-10-28 (fabric-coordinator)*
