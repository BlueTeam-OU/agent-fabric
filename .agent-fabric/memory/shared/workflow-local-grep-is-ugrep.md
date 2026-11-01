---
role: shared
class: workflow
topic: "local-grep-is-ugrep"
description: "\"grep is ugrep\" on a login is the Claude Code Bash tool's shell function; children (run.sh, hooks, CI-like subprocesses) get GNU grep"
tier: 1
knowledge_scope: full
shared_with:
  - "fabric-coordinator"
  - "python-dev"
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 664189f0ec234df7
  - c7e1960d5cdd2821
---

## "grep is ugrep" on a login is the Claude Code Bash tool's shell function; children (run.sh, hooks, CI-like subprocesses) get GNU grep

The ugrep seen on some logins is not provisioning and not PATH. The Claude
Code Bash tool's shell snapshot defines `grep` (and `find`) as shell
functions over the harness binary (ugrep, version of the claude binary, so it
moves with `upgrade claude`). `/usr/bin/grep` is GNU 3.12 and no ugrep file
exists on the host. Re-verified 2026-10-25: `type grep` at the tool's top
level is a function; `bash -c 'type grep'` is /usr/bin/grep.

**Why:** the two greps fold case differently (U+0131 under -i), so a grep typed
at the tool's top level can disagree with what a script, hook or guard runs.
Provisioning needs no pin; the earlier slice's "consider pinning static.sh" is
moot for children, which already get GNU grep.

**How to apply:** to reproduce a grep-based guard, run `/usr/bin/grep` or
`command -p grep` explicitly, or `bash -c`; a top-level `grep` result is the
harness's, not CI's. Verify with `type grep` before blaming a login's setup.

*Observed 2026-10-25 (python-dev)*
