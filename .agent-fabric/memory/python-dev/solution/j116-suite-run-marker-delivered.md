---
role: "python-dev"
class: solution
topic: "j116-suite-run-marker-delivered"
description: "j116: resume.py SUITE_MARKER renamed to AGENT_FABRIC_SUITE_RUN, branch a08f5587 pushed, INFO to coordinator; their run.py part pending"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 68f54092cc2ecafe
---

## j116: resume.py SUITE_MARKER renamed to AGENT_FABRIC_SUITE_RUN, branch a08f5587 pushed, INFO to coordinator; their run.py part pending

Delivered 2026-11-05 on `develop-qzapp/python-dev-02/feat/j116-490-distributed-yes-to-agent-fabric` (a08f5587, no PR; INFO seq 846822 to fabric-coordinator). Coordinator's run_environment must set AGENT_FABRIC_SUITE_RUN=1; until it lands suites carry no marker.

**Why:** the for/user/suite-run-marker branch was still checked out in the j115 worktree, and the job hook refuses commits outside the session's job copy, so the commit went on the job's feat branch.

**How to apply:** the hook reads the whole command line, so a command that cd's into another worktree to commit is refused; revert there with `git -C` and redo in the job copy.

*Anchors: `tools/fabric/resume.py::SUITE_MARKER`*

*Observed 2026-11-05 (python-dev)*
