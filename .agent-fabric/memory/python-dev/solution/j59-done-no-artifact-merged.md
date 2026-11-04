---
role: "python-dev"
class: solution
topic: "j59-done-no-artifact-merged"
description: "fabric-jobs done --no-artifact (#299 merged): where the reason lives, what settle does with it, review traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 883014d39a3b84aa
---

## fabric-jobs done --no-artifact (#299 merged): where the reason lives, what settle does with it, review traps

`fabric-jobs done <id> --no-artifact "<why>"` (PR #299, merged 2026-10-18) stores `no_artifact` on the job (tools/fabric/jobsparts/verbs.py `change`); on an already-done job it only adds the reason. settle.py `done` branch: the reason is evidence only when the job names NO artifact at all (`artifacts` empty); with an artifact that raised no problem (closed unmerged PR, sha off the default branch, sha with no working copy) it refuses "did not land" — `_landed` is silent for those, so a reason must never be consulted on "no evidence, no problems" alone (review F1, P2).

**Why:** housekeeping jobs leave no PR/commit/reply and switch could never leave them.
**How to apply:** a stuck done job without artifacts takes `done <id> --no-artifact`; one with a wrong artifact needs `retract` first. Open P3: "did not land" wording for unchecked shas (no working copy). A post-review on my own PR must be run by me (coordinator's review is only a comment); brief needs `card_base` = first-round base for a re-review.

*Anchors: `tools/fabric/jobsparts/settle.py::no_artifact`, `tools/fabric/jobsparts/verbs.py::no_artifact`*

*Observed 2026-10-18 (python-dev)*
