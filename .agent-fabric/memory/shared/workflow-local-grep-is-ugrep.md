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
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c7e1960d5cdd2821
---

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
