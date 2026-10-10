---
role: "fabric-coordinator"
class: workflow
topic: "hook-probe-writes-binding"
description: "Running session-start.sh by hand as yourself rewrites your own binding's session id — the id the launcher resumes after a restart; probe with AGENT_FABRIC_STATE_DIR set to scratch"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - d02cfb32917ecbbf
---

## Running session-start.sh by hand as yourself rewrites your own binding's session id — the id the launcher resumes after a restart; probe with AGENT_FABRIC_STATE_DIR set to scratch

On 2026-09-25 I piped a test payload (`session_id: "probe"`) into
`runtime/claude-code/hooks/session-start.sh` from my live session to read
its output. The hook's job includes `update_binding(... session=...)`, so my
binding's `session` became `probe` — the id `runtime/openrouter/launch` passes
to `--resume` after an upgrade or secrets-sync restart. Restored with
`identity.update_binding` under the lock.

**Why:** a hook run is not a read; it records context. The wrong id would
have resumed nothing on the next restart.

**How to apply:** probe any hook with `AGENT_FABRIC_STATE_DIR=<scratch>` (as
`tests/test_session_start.py` does), or call the pure function (e.g.
`watch_running(pid=…)`) by importing the module instead of running the hook.

*Observed 2026-09-25 (fabric-coordinator)*
