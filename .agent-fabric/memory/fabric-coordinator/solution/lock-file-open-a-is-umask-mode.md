---
role: "fabric-coordinator"
class: solution
topic: "lock-file-open-a-is-umask-mode"
description: "when reviewing or writing a flock lock file under agents/<login>/ — open(path, \"a\") gives the umask's 0644, not the 0600 ADR-003 §2 requires"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric-j511-drain-2026-10-31-fabric-half"
derived_from:
  - 68629cc4ce390004
---

## when reviewing or writing a flock lock file under agents/<login>/ — open(path, "a") gives the umask's 0644, not the 0600 ADR-003 §2 requires

`open(path + ".lock", "a")` creates the lock file with the umask's mode (0644 under 022). ADR-003 §2 (A 2026-10-31) says a lock file
is not state only when it is opened without O_TRUNC, **mode 0600**, and never written, read or removed. The compliant open is
`os.open(path, O_WRONLY|O_CREAT|O_CLOEXEC|O_NOFOLLOW, 0o600)`, as `pool._locked` and session-state.py's `open_lock` do (j487,
agent-fabric #451 a0d0f2c0, ADR-003 A 2026-11-01). Test it under an explicit `os.umask(0o022)`: an inherited umask of 077 hides it.

Still open: tools/fabric/fabric_writes.py and tools/fabric/gh_ledger.py (job j535). Both also compute the state dir on their own
instead of through identity.py.

A hook that writes per-agent state loads identity.py lazily, by the hook's own place in the tree, and only when it has something to
write: PreToolUse fires on every tool call, and loading identity.py is most of the hook's run time.

*Anchors: `runtime/claude-code/hooks/session-state.py::def open_lock`, `tools/fabric/fabric_writes.py::open(path + ".lock", "a")`, `tools/fabric/gh_ledger.py::open(path + ".lock", "a")`*

*Observed 2026-11-01 (fabric-coordinator)*
