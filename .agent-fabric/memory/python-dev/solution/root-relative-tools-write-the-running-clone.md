---
role: "python-dev"
class: solution
topic: "root-relative-tools-write-the-running-clone"
description: a test that runs a tool finding its root from its own path (bootstrap.sh) writes the clone running the suite; invisible under projects/, seen only from a scratch clone
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 95747f3388a7099e
---

## a test that runs a tool finding its root from its own path (bootstrap.sh) writes the clone running the suite; invisible under projects/, seen only from a scratch clone

runtime/claude-code/bootstrap.sh finds the fabric root from its own path and sets that checkout's core.hooksPath (step 4). tests/test_session_start.py ran it in place, so every suite run wrote the running clone's .git/config. Under ~/projects/agent-fabric the value was already set, so nothing showed; devex-tooling saw it in a scratch clone outside projects/ (#89 carried item 4).

Fixed on develop-qzapp/python-dev-01/for/user/carried-89 (6e7059f): the cases run bootstrap from `fabric_copy(tmp)` (tracked + untracked-not-ignored files, git init + commit), and main() fails when `git config --local --list` of the running clone differs after the cases.

**How to find one:** clone the branch into scratch outside projects/, unset the value, run each candidate test file from the clone with CI's env, read the config after each (`git -C clone config --get core.hooksPath`). Took one loop over five files.

**How to apply:** any test that runs a script by its path in the tree (bootstrap, a launcher, an installer) runs the tree's copy, not a fixture; ask what that tool writes under its own root. Related: [[env-isolation-in-process-environ]], [[fake-tools-must-sit-on-the-callees-path]].

*References: env-isolation-in-process-environ, fake-tools-must-sit-on-the-callees-path*

*Observed 2026-10-04 (python-dev)*
