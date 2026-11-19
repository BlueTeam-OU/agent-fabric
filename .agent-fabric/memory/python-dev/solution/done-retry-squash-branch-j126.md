---
role: "python-dev"
class: solution
topic: "done-retry-squash-branch-j126"
description: "j126 #542 — fabric-jobs done retries a squash-merged branch with all named artifacts; review rounds, the P3 carried, workflow traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 268483b68f7f6e64
---

## j126 #542 — fabric-jobs done retries a squash-merged branch with all named artifacts; review rounds, the P3 carried, workflow traps

#542 (merged): in `verbs.move` each `done` name is judged alone (`_unlanded`); only a refusal containing `settle.NO_PR_AT_TIP` is retried with all names, and leftovers are reported together ("<name> with the names beside it is not recorded"), never blamed on one name. Widening the retry to any problem lets an unrelated landed artifact excuse a closed PR (the existing merged-beside-closed test is the mutation catcher). `done_evidence` always adds a "done needs evidence" problem when nothing landed, so an empty problems list is a pass (a reviewer's "nothing landed" fallback finding was wrong: check the callee before adding a fallback).
Carried P3 (deferred 3058007b:F1): one argv string with several references ("branch #7") is judged whole; "#4 #7" already passes on main. Follow-up: one-name-one-reference rule.
**Workflow traps:** a delivered job must be `fabric-jobs start`ed again before any commit (guard); a command mixing `$HOME`-using env -i with `git commit/push` is refused by the job-copy guard, so run tests and git separately; every commit after a review makes a new head, so batch P3 fixes and the main merge before the one review to post; the post-review report is written verbatim with Write.

*Anchors: `tools/fabric/jobsparts/verbs.py::_unlanded`, `tools/fabric/jobsparts/settle.py::NO_PR_AT_TIP`*

*Observed 2026-11-10 (python-dev)*
