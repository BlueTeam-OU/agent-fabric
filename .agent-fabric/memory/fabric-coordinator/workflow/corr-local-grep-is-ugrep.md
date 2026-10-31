---
role: "fabric-coordinator"
class: workflow
topic: "corr-local-grep-is-ugrep"
description: "Only a command typed at the Bash tool's top level gets the harness's ugrep `grep`; scripts, hooks, guards and tests/run.sh run GNU /usr/bin/grep, so compare a measurement against a guard with /usr/bin/grep"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0850a89e30dac4d5
  - c6aac5efefa6edeb
---

## Only a command typed at the Bash tool's top level gets the harness's ugrep `grep`; scripts, hooks, guards and tests/run.sh run GNU /usr/bin/grep, so compare a measurement against a guard with /usr/bin/grep

In a Claude Code session the Bash tool's shell snapshot defines `grep` (and `find`) as a shell function ("Shadow find/grep with embedded bfs/ugrep") that runs the claude binary as ugrep. The function is not exported. `bash -c`, `sh -c`, a script, a python subprocess and `shutil.which` all resolve GNU `/usr/bin/grep`. Measured by python-dev-04 on Claude Code 2.1.286, 2026-10-24. No login has a ugrep file on the host, and provisioning sets no grep path. The ugrep version moves with `upgrade claude`.

So tests/static.sh, the hooks and the guards run GNU grep everywhere. The difference shows only in what I type at the top level, for example a case fold: U+0131 under `-i` matches with GNU grep and does not with ugrep. A top-level grep and a script's grep can disagree on the same input.

**Why:** a check I typed at the top level can disagree with the guard it is meant to reproduce. The earlier reading (the whole login is ugrep, so a local static.sh run differs from CI) blamed the wrong layer.
**How to apply:** when a grep result at the Bash tool has to match a guard, a test or CI, run `/usr/bin/grep` (or `command grep`). A local-versus-CI difference in a script needs another cause. Code that needs GNU semantics names `/usr/bin/grep`.

*Observed 2026-10-25 (fabric-coordinator)*
