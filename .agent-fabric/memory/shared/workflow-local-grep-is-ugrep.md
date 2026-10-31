---
role: shared
class: workflow
topic: "local-grep-is-ugrep"
description: "On develop-qzapp `grep` resolves to ugrep — tests/static.sh's sh-shebang check passed locally and failed in CI; verify a grep-based guard with /usr/bin/grep before trusting a local green"
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

*Anchors: `tests/static.sh::grep`*

*Observed 2026-10-25 (python-dev)*

## On develop-qzapp `grep` resolves to ugrep — tests/static.sh's sh-shebang check passed locally and failed in CI; verify a grep-based guard with /usr/bin/grep before trusting a local green

On the coordinator's login `grep` is ugrep (the shell prints
"ugrep: warning: …" for a missing file). `tests/static.sh`'s
one-dialect check (`grep -lE '^#!/bin/sh|…'` over every script) printed
"all bash scripts parse" locally on 2026-09-19 while CI's GNU grep
found the `#!/bin/sh` inside a stub heredoc of a lifted test
(`runtime/github/test_post-substitute-review.sh:63`, PR #19).

**Why:** a guard that reads differently under two greps is green on
the machine that matters least. CI is the authority; a local static
pass is a hint.

**How to apply:** before pushing a change to a shell-script set, run
the shebang check with `/usr/bin/grep` explicitly, or run the static
suite in the podman smoke container (see [[smoke-container-before-ci]]).
Consider pinning `static.sh` to `command -p grep` — a fabric change,
not yet made.

*References: smoke-container-before-ci*

*Observed 2026-09-19 (fabric-coordinator)*
