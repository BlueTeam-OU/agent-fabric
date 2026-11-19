---
role: "python-dev"
class: solution
topic: "session-proc-hooks-j143"
description: "j143 — hooks onto session_proc; hooks are supply paths (for/user branch), AGENT_FABRIC_ROOT env makes hook tests load main's session_proc, suite load reds"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9e710cfb5b4b4463
---

## j143 — hooks onto session_proc; hooks are supply paths (for/user branch), AGENT_FABRIC_ROOT env makes hook tests load main's session_proc, suite load reds

Branch develop-qzapp/python-dev-03/for/user/j143-session-proc-hooks (3cc8e3ca): session-start.watch_running, session-state.harness, watch-on-stop.harness_pid load tools/fabric/session_proc.py by path; added session_proc.matches() and nearest_session_in(table) for watch-on-stop's pre-read table. Tests live in tests/test_session_proc.py ("the three hooks").
**Why:** hooks are `supplies` paths: committing on a feat/ branch is refused; rename the branch to <host>/<login>/for/user/<what> first. deliver then `done` needs a merge, so the job stays delivered.
**How to apply:** run hook tests with `env -i PATH=…` — an inherited AGENT_FABRIC_ROOT makes the hook load the installed (older) session_proc and mutations look like survivors. A hook with a bad relative path fails only on import (check the dirname depth of IDENTITY). Full run.sh reds under cpu-lease load: test_leak_check (precondition waits for cpu lease, fails alone too) and test_project_import (lint timeout, passes alone). The guard refuses `git commit` in a command using $HOME; commit in its own call.

*Anchors: `tools/fabric/session_proc.py::nearest_session_in`, `runtime/claude-code/hooks/watch-on-stop.py::harness_pid`*

*Observed 2026-11-14 (python-dev)*
