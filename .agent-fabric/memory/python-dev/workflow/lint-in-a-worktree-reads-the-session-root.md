---
role: "python-dev"
class: workflow
topic: "lint-in-a-worktree-reads-the-session-root"
description: "tools/fabric/lint.py run from a contributor worktree with the session's AGENT_FABRIC_ROOT lints ~/projects/agent-fabric (main), not the worktree — a green \"lint clean\" that is not about your branch"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 64bf3464625bfc23
---

## tools/fabric/lint.py run from a contributor worktree with the session's AGENT_FABRIC_ROOT lints ~/projects/agent-fabric (main), not the worktree — a green "lint clean" that is not about your branch

In the carried audit (2026-10-04, branch
develop-qzapp/python-dev-01/for/user/carried-audit) a comment pushed
runtime/provisioning/new-agent-worker.sh to 154 lines, over the 150-line
bash limit (not on policies/bash-allowlist.json). `python3 tools/fabric/lint.py`
run in the worktree said 0 every time; tests/run.sh with CI's environment
failed on "corpus lint". The session exports AGENT_FABRIC_ROOT pointing at
the main checkout, and lint checks that root. With `env -u AGENT_FABRIC_ROOT`
it failed on the committed tree (the control) and passed on the fix.

**Why:** the remit asks for lint clean before every commit; with the
session's root it is lint of main, which proves nothing about the branch.
**How to apply:** in a worktree, run `env -u AGENT_FABRIC_ROOT python3
tools/fabric/lint.py` (and every test the same way). Related:
[[suites-inherit-launch-stamps]].

*References: suites-inherit-launch-stamps*

*Observed 2026-10-03 (python-dev)*
