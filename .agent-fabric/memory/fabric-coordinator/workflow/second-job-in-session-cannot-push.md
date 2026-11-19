---
role: "fabric-coordinator"
class: workflow
topic: "second-job-in-session-cannot-push"
description: "Starting a second job mid-session blocks git push (ADR-037 rule 3 hook), and pause refuses an unpushed branch: commit the second job's work only from a fresh session"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 129665a2d704aa2c
---

## Starting a second job mid-session blocks git push (ADR-037 rule 3 hook), and pause refuses an unpushed branch: commit the second job's work only from a fresh session

2026-11-10, j706 → j732 in one session: the owner's mid-session request made me block j706, start j732 and commit b1b8ce3d on j706's branch. Then the PreToolUse hook refused `git push` (j732 "belongs to a fresh session"), and `fabric-jobs pause j732` refused because the branch was not on origin. That is a deadlock. The way out was `fabric-jobs block j732 … --on clock:<soon>` (block does not check the push), then `fabric-jobs switch`.

**Why:** the hook binds publishing to the session's first job; pause guards unpushed work.
**How to apply:** when the owner asks for new work mid-session, take it as a job and draft it, but commit and push it from the fresh session `switch` prints. If a commit is already made, block (not pause) the job with the sha in the note. Related: [[jobs-and-switching]].

*References: jobs-and-switching*

*Observed 2026-11-10 (fabric-coordinator)*
