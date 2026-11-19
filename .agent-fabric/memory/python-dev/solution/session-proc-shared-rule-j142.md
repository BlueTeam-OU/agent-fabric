---
role: "python-dev"
class: solution
topic: "session-proc-shared-rule-j142"
description: "j836/#606 — one rule for a session's claude process under 2.1.322 (daemon is comm claude, session is version-named); hook walks left"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f62a49068bd49bdf
---

## j836/#606 — one rule for a session's claude process under 2.1.322 (daemon is comm claude, session is version-named); hook walks left

tools/fabric/session_proc.py (#606): session = nearest ancestor with comm `claude` or dotted-version comm whose argv[1] != "daemon"; unreadable cmdline stays a session. Under 2.1.322 bg-pty-host the daemon is comm `claude`, session is `2.1.322` below bg-pty-host < daemon. status, gzcoord session.py, fresh.py use it; review_brief/self-kill-guard are the owner's (never-list); session-start.py:427, session-state.py:103, watch-on-stop.py:115 are j143 (for/user branch, a test each).
**Why:** old walks stopped at the daemon. **How to apply:** new /proc walks call session_proc.nearest_session; fake-/proc tests need `stat` files; a `seen` set is redundant with MAX_HOPS (mutation survived); fabric-pr gate counts before every status line (Stop hook); re-review request must omit previous_findings; push needs `-c 'credential.helper=!gh auth git-credential'`.

*Observed 2026-11-14 (python-dev)*
