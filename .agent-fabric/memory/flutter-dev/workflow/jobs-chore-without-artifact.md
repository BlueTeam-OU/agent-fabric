---
role: "flutter-dev"
class: workflow
topic: "jobs-chore-without-artifact"
description: "recording a chore that lands nothing (e.g. a REPLY-EXPECTED: no broadcast's disk cleanup) in fabric-jobs — drop it with the reason, never mark it done"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "flutter-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a7746ca68c67bc5b
---

## recording a chore that lands nothing (e.g. a REPLY-EXPECTED: no broadcast's disk cleanup) in fabric-jobs — drop it with the reason, never mark it done

`fabric-jobs done` settles only with landed evidence: a merged PR, a commit on origin's default branch, a branch on
origin, or `reply:<MESSAGE-ID>` of a reply this login sent (tools/fabric/jobsparts/settle.py `_landed`, `_replies`).
A home-only chore asked by a broadcast with `REPLY-EXPECTED: no` (the 2026-10-17 disk cleanup, 01a14a95) has none
of these, and a done job cannot be dropped afterwards ("a closed job is not reopened"), so `switch` then refuses to
leave it.

**Why:** j8 (2026-10-17) was added to carry the cleanup's one-line note and marked done; `switch` refused it and it
could not be moved to dropped.

**How to apply:** for a chore with no artifact, `fabric-jobs add "<one-line note>"`, `start`, then
`fabric-jobs drop <id> "<what was done, and why nothing lands>"` — `dropped` settles on its reason alone.
Related: [[jobs-reply-evidence]].

Fixed (2026-10-18): agent-fabric #299 merged (c6b0fc61) — `fabric-jobs done <id> --no-artifact "<what was done>"`
is the way to close work that lands nothing in a repository, including a job already stuck done (j8 was settled
that way). Prefer it to add-then-drop.

*References: jobs-reply-evidence*

*Anchors: `tools/fabric/jobsparts/settle.py::_landed`, `tools/fabric/jobsparts/settle.py::done needs evidence it landed`*

*Observed 2026-10-18 (flutter-dev)*
