---
role: "devex-tooling"
class: domain
topic: "find-a-process-by-pid-not-name"
description: "a process found by name pattern (pgrep -x / -f, pkill -f) misses or mis-hits: comm is cut to 15 chars, a forwarder execs a differently named file, the session's own prompt matches; keep the PID the launcher gives"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c0fa761953072aa9
---

## a process found by name pattern (pgrep -x / -f, pkill -f) misses or mis-hits: comm is cut to 15 chars, a forwarder execs a differently named file, the session's own prompt matches; keep the PID the launcher gives

Three ways a name lookup went wrong on develop-qzapp:

- **comm is cut to 15 characters** (2026-09-25). `pgrep -x` matches comm, so
  `Gzapp.PassengerApi.Tests` is stored as `Gzapp.Passenger`. A pattern like `Gzapp\..*\.Tests` in
  gzapp's prune-testcontainers liveness guard matched nothing, and pgrep itself warns about it.
- **The session's own command line matches** (2026-09-29). Each claude process was launched with a
  prompt containing `gzcoord-inbox --follow`. So `pkill -f` on that pattern, meant to tidy stale
  watchers, ended the session itself. fabric-coordinator fixed the prompt and added a kill guard.
- **A forwarder execs another name** (2026-10-08). Since gzapp #1056, `tools/gh/wait-merged.sh`
  execs fabric-python on `tools/fabric/github/wait_merged.py`, with an underscore.
  `pgrep -af wait-merged` finds no live watcher, so a session may start a second one. Three slices
  taught that lookup.

**How to apply:** keep the PID the launcher or the harness's background mode reports, and ask about
that PID (`kill -0`, `ps -p`). When a name lookup is unavoidable:
- use `pgrep -u "$(id -un)" -af` and read the lines rather than act on them;
- treat a line starting `claude` as yourself;
- never `pkill -f`;
- remember that a wrapper's name is not its child's.
When a tool moves behind a forwarder, grep the docs and slices for lookups by its old name.

*Observed 2026-10-22 (devex-tooling)*
