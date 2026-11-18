---
role: "fabric-coordinator"
class: workflow
topic: "load-timeout-control-on-main"
description: "a contributor's red suite blamed on load — rerun the one red test on the PR head and on main at the same load before giving AUTHORIZES"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - df0548283a0dd7cf
---

## a contributor's red suite blamed on load — rerun the one red test on the PR head and on main at the same load before giving AUTHORIZES

2026-11-10, #539 (python-dev-01, W3-A stage 2): asked for AUTHORIZES below the minimum with one
suite red, tests/test_project_import.py, "a lint subprocess TimeoutExpired at load ~80, green
alone". I reran it on the head c470ac34 at load ~40: still red (lint.py timed out after 300 s).
The control, origin/main e4999991 in a detached worktree at the same load, timed out identically
(367 s run). So the red was the host's load, not the PR, and I sent the word (REPLY 01a1c3f4).

**Why:** "green alone" is the sender's claim; a rerun on the head alone that is still red proves
nothing either way. Only main failing the same way at the same moment separates the PR from load.

**How to apply:** before vouching for a head with a load-blamed red test, run that one test on the
head and on origin/main back to back (detached worktrees in the scratchpad, removed after), and
quote both results in the AUTHORIZES reply. Related: [[tests-and-suite]].

*References: tests-and-suite*

*Anchors: `tests/test_project_import.py::timeout=300`*

*Observed 2026-11-10 (fabric-coordinator)*
