---
role: "flutter-dev"
class: workflow
topic: "blocked-job-notes-outlive-the-session"
description: "Before a job blocks across sessions, put its working notes in the job itself or a pushed branch — fabric-branches --sweep deletes an ended session's scratchpad whole"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a53909959dbdac0f
---

## Before a job blocks across sessions, put its working notes in the job itself or a pushed branch — fabric-branches --sweep deletes an ended session's scratchpad whole

`fabric-branches --sweep` (agent-fabric #339, e18a5ffe) deletes every ended session's
scratch under the harness tmp root, CLAUDE_CODE_TMPDIR included. On 2026-10-20 it took
the 2026-10-10 session folder, and with it j26's local notes on gzapp ADR-078 (what the
rider capture showed, what the driver capture must check) — j26 was blocked on the
owner, so the notes were still needed.

**Why:** the scratchpad belongs to one session; a blocked job outlives it, and the sweep
cannot tell notes from leftovers.

**How to apply:** when a job blocks, write what the next session needs into the job
(`fabric-jobs block <id> "<reason + findings>"`), a commit on the job's pushed branch, or
a memory — never only the scratchpad. Scratch is for what dies with the session.

*Anchors: `tools/fabric/branches.py::claude_tmp_roots`*

*Observed 2026-10-21 (flutter-dev)*
