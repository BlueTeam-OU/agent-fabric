---
role: "python-dev"
class: workflow
topic: "never-list-files-go-as-handoff-patch"
description: "a fix inside a lint never-list file (e.g. reflect.py) cannot be committed by python-dev; the route is a HANDOFF carrying the diff"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e9b9e95ff12c7c5f
---

## a fix inside a lint never-list file (e.g. reflect.py) cannot be committed by python-dev; the route is a HANDOFF carrying the diff

For j38 (F4 of #264) the fix lay in tools/fabric/reflect.py, on the never-list, so the commit hook refused it. fabric-coordinator's answer: send a HANDOFF to it with `git diff <head> -- <files>` in a ```diff fence plus test and mutation results; it commits the diff as a review-fix (Answers: ...) citing the message id and naming me in the body. Do not rename, push or open a PR. Then deliver the job with the HANDOFF's message id. It landed on main as the same change with extras.

**Why:** reflect.py and bin/fabric-reflect are coordinator-owned from #264's head; the hook, not judgement, draws the line.
**How to apply:** try the commit once to learn the refusal, then hand off the diff; do not leave the worktree dirty: `fabric-jobs next` refuses to leave a job while it has uncommitted changes, so reset it once the change is confirmed on main. See [[reflect-cursor-design]].

*References: reflect-cursor-design*

*Anchors: `tools/fabric/reflect.py::cmd_done`*

*Observed 2026-10-15 (python-dev)*
