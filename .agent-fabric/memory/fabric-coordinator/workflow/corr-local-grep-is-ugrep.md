---
role: "fabric-coordinator"
class: workflow
topic: "corr-local-grep-is-ugrep"
description: "On the coordinator's login grep is ugrep; verify a grep-based guard with /usr/bin/grep before trusting a local green"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c6aac5efefa6edeb
---

## On the coordinator's login grep is ugrep; verify a grep-based guard with /usr/bin/grep before trusting a local green

In a Claude Code session `grep` is a shell function that runs the harness's embedded ugrep (checked 2026-10-11: `type grep` shows it, it prints "ugrep: warning: ..." for a missing file). `tests/static.sh`'s one-dialect check (`grep -lE '^#!/bin/sh|^#!/usr/bin/env sh'` over every script, still plain `grep`, not pinned to `command -p grep`) printed "all bash scripts parse" locally on 2026-09-19 while CI's GNU grep found the `#!/bin/sh` inside a stub heredoc of a lifted test (PR #19; that test file has since been retired).

**Why:** a guard that reads differently under two greps is green on the machine that matters least. CI is the authority; a local static pass is a hint.

**How to apply:** before pushing a change to a shell-script set, run the shebang check with `/usr/bin/grep` explicitly, or run the static suite in the podman smoke container (see [[smoke-container-before-ci]]). Pinning `static.sh` to `command -p grep` is still a fabric change not yet made; propose it to fabric-coordinator's own lane rather than assume it.

*References: smoke-container-before-ci*

*Observed 2026-10-11 (fabric-coordinator)*
