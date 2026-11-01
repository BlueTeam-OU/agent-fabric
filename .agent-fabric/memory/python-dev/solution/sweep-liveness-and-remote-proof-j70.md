---
role: "python-dev"
class: solution
topic: "sweep-liveness-and-remote-proof-j70"
description: "j70 #330 fabric-branches --sweep traps: session liveness source, stale tracking refs, test isolation of the registry, security-boundary arming"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b3b2bc2630d6052c
---

## j70 #330 fabric-branches --sweep traps: session liveness source, stale tracking refs, test isolation of the registry, security-boundary arming

#330 (tools/fabric/branches.py, jobsparts/leave_sweep.py): the claude harness process has no CLAUDE_CODE_SESSION_ID in its own environ, so a live session is found from the registry `~/.claude/sessions/<pid>.json` with `plan_hold.alive(pid, procStart)`, never a /proc environ scan. "Pushed" is proved with `git ls-remote` name+sha, not remote-tracking refs (stale after the branch is deleted remotely). `git worktree remove` deletes ignored files, so ignored non-bytecode files need `status --porcelain --ignored -uall`. The control agent parses sweep lines with fullmatch regexes: keep "removed worktree P"/"KEPT ..." unchanged, add new info on following lines.

**Why:** tests that ran a sweep against the real registry removed my own ended sessions' scratch; every suite that runs a sweep must set CLAUDE_CONFIG_DIR to a nonexistent dir (guard test in tests/test_branches_sweep.py).

**How to apply:** any new code touching sessions or sweeps. Arming: a PR touching a security-boundary file (control/branches_op.py) under 8 work commits needs the coordinator's `AUTHORIZES:` DECISION (--authorization id); GitHub REST rate limit blocks arm ("policy cannot be read") until reset, retry then.

*Anchors: `tools/fabric/branches.py::live_sessions`, `tools/fabric/branches.py::remote_refs`, `tools/fabric/jobsparts/leave_sweep.py::after_leaving`*

*Observed 2026-10-20 (python-dev)*
