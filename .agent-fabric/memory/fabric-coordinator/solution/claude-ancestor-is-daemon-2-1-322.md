---
role: "fabric-coordinator"
class: solution
topic: "claude-ancestor-is-daemon-2-1-322"
description: "a nearest-'claude'-ancestor lookup finds `claude daemon` (cwd /home/user), not the session, under 2.1.322 bg-pty-host; fixed by session_proc.nearest_session (#606 + j836 branch)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 59d3651d41963308
---

## a nearest-'claude'-ancestor lookup finds `claude daemon` (cwd /home/user), not the session, under 2.1.322 bg-pty-host; fixed by session_proc.nearest_session (#606 + j836 branch)

Seen 2026-11-13 on j800: a Bash call's ancestry was bash < `2.1.322 --session-id …`
(the session itself; comm is the version string, exe ~/.local/share/claude/versions/2.1.322,
cwd = the working copy) < `claude bg-pty-host` < `claude daemon run --origin transient`
(comm `claude`, cwd /home/user) < the launched `claude --model …`. Every lookup that
takes the nearest comm == "claude" lands on the daemon: `fabric-review brief` refused
"the session was started in /home/user". The review MCP server itself read the clone
fine (CLAUDE_PROJECT_DIR).

Workaround for a brief: `FABRIC_REVIEW_SESSION_CLONE=$PWD fabric-review brief …`
(true only when $PWD is the session's clone; check a review MCP call reads the head).
Same pattern in tools/fabric/status.py, gzcoord inbox_parts/session.py SESSION_COMM,
runtime/claude-code/hooks/self-kill-guard.py, tools/fabric/fresh.py — job j836.
Related: [[session-clone-from-claude-cwd]].

Bitten again 2026-11-13: `fabric-fresh --job j833` stopped the `claude
daemon` (its session_pid takes the nearest comm "claude"), printed "ending
this session", and the session lived on under a reparented bg-pty-host;
the launcher's foreground `claude` never exited, so no relaunch. Restart
marker was written. Recovery: stop the launcher's `claude` and the
bg-pty-host by pid together. j836 must cover tools/fabric/fresh.py too.

Fixed 2026-11-14: the rule is tools/fabric/session_proc.py (nearest_session; daemon
excluded by argv[1] == "daemon", version comm accepted), landed in #606 (python-dev-03,
fresh/status/gzcoord); hooks session-start/session-state/watch-on-stop (python-dev-03 supply
j143) and review_brief + self-kill-guard folded on branch j836 (commit 403dc692).
self-kill-guard is a managed hook: it uses the new rule only after the owner reinstalls the
managed snapshot at a sha that has it. Open: #606 F3 (stale watch mark records the daemon pid).

*References: session-clone-from-claude-cwd*

*Anchors: `tools/fabric/review_brief.py::def dispatching_session_pid`, `tools/fabric/gzcoord/inbox_parts/session.py::SESSION_COMM`, `runtime/claude-code/hooks/self-kill-guard.py::SESSION_NAME`*

*Observed 2026-11-13 (fabric-coordinator)*
