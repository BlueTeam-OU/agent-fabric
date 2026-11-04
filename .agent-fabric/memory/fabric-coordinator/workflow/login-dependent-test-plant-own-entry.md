---
role: "fabric-coordinator"
class: workflow
topic: "login-dependent-test-plant-own-entry"
description: "a suite case that fails only for another login (its agent layer in routing/profiles.json) — reproduce by planting my own login's entry in the worktree, then restore"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e333c3421685ab57
---

## a suite case that fails only for another login (its agent layer in routing/profiles.json) — reproduce by planting my own login's entry in the worktree, then restore

A test failing "only for python-dev-03" (j438, PR #436) came from code the
suite runs from the real tree (tools/fabric/resume.py, FABRIC = its own
checkout) reading the live routing/profiles.json agent layer. To reproduce it
I did not need that login: I added `agents.user.launch_provider: anthropic` to
the worktree's routing/profiles.json and ran the group, which gave 19 FAILs.
Then I made the fix (default the fixture override in the test's run()) and
re-ran with the plant still in, which passed. Last, `git checkout routing/profiles.json`.

**Why:** the control shows the fix covers the actual cause. A green run on my
own login proves nothing, because my login has no agent entry.
**How to apply:** for any "fails for login X" report, look for an
`os.environ.get(...) or roots.*(engine=FABRIC)` read in code the launcher loads
from the real tree, plant X's layer for my login, and keep the plant through
the whole-file run. Related: [[checks-need-a-control]].

*References: checks-need-a-control*

*Anchors: `tools/fabric/resume.py::AGENT_FABRIC_RESUME_PROFILES`, `tests/test_launch_cli.py::AGENT_FABRIC_RESUME_PROFILES`*

*Observed 2026-10-30 (fabric-coordinator)*
