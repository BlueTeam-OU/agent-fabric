---
role: "backend-dev"
class: workflow
topic: "pgrep-wait-loop-self-match"
description: "A background \"wait until no dotnet build runs\" loop using pgrep -f deadlocks on its own command line"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "backend-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 23c32d108d4c18f4
---

## A background "wait until no dotnet build runs" loop using pgrep -f deadlocks on its own command line

A background Bash of the shape `while pgrep -f "dotnet build ..."; do sleep 5; done; dotnet build ...`
never exits: the harness runs it as `bash -c '<whole command>'`, so `pgrep -f` matches the
loop's own command line (and a second such loop matches the first). Two queued builds on
backend-dev-01's j41 worktree (2026-10-19) sat idle for over an hour this way.

**Why:** pgrep -f matches the full argv of every process, including the shell running the pattern.

**How to apply:** never queue builds behind a pgrep wait. Chain them in ONE background command
(`dotnet build Gzapp.sln && dotnet test --no-build ...`), or stop the earlier task with TaskStop
first. Killing by pattern is refused by the fabric's hook; stop a background task with TaskStop.

*Anchors: `agent-fabric/AGENTS.md::fabric-lease`*

*Observed 2026-10-19 (backend-dev)*
