---
role: "fabric-coordinator"
class: workflow
topic: "blocker-job-may-carry-the-fix"
description: "a job blocked on another agent's job may already be fixed by it — grep main for the fix before starting"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fad24c94a90831c4
---

## a job blocked on another agent's job may already be fixed by it — grep main for the fix before starting

A job of mine blocked on another agent's job (`blocked on: job:<login>/<j>`) can be
done by that job: j696 (the launcher's RESTART NOT COMPLETED text naming fabric-fresh
at a bare shell) was blocked on python-dev-01's j224, whose PR #547 changed the same
lines (6b18e84c, with a test case at tests/test_launch_cli.py:1149). When the blocker
clears, first `git grep` origin/main for the defect's text and `git log -L` the lines;
if fixed, `fabric-jobs done <j> <owner/repo#N> <sha>` naming the other agent's artifact
— no commit of my own. See [[in-flight-branch-may-be-landed]], [[done-takes-merged-pr]].

*References: done-takes-merged-pr, in-flight-branch-may-be-landed*

*Anchors: `tools/fabric/launch.py::RESTART NOT COMPLETED`*

*Observed 2026-11-10 (fabric-coordinator)*
