---
role: "python-dev"
class: solution
topic: "j41-settle-reflection-cursor-merged"
description: "#274 merged (6619345f): settle.py reflection cursor, reply:<id> by own id, retract, any-answer; foll"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 941e256de7c39bf8
  - b2e47b290ff1173f
---

## #274 merged (6619345f): settle.py reflection cursor, reply:<id> by own id, retract, any-answer; foll

#274 (7 work, 2 fix) merged 2026-10-16 as 6619345f. settle.py: topic=reflection settles on the fabric-reflect cursor (done_at > job start); `replied()` and `owed_replies()` read any outbound row with IN-REPLY-TO (not only type REPLY); `fabric-jobs retract <id> <artifact>` removes one artifact in any state. Checked against origin/main 2026-10-20: all three still hold.

The follow-up list in the first version is DONE: the empty-header and failed/pending-send cases landed in #277 (`_ANSWERS`), the blockers disagreement in #279, and `done --no-artifact` (#299, ac3f129a) means a done reason counts only for a job that names no artifact.

**Why:** a reflection pass lands no PR/sha; a DECISION answers a REQUEST; `gzcoord-send` prints only the reply's own id.

**How to apply:** traps still met: `git push` has no credential helper in this account (use `-c credential.helper='!gh auth git-credential'`); full tests/run.sh gzcoord/launch/lease suites time out under host load and pass alone; below 8 work commits `fabric-pr arm` needs the owner's actual word in --basis.

*Anchors: `tools/fabric/jobsparts/settle.py::_reflected`, `tools/fabric/jobsparts/settle.py::replied`, `tools/fabric/jobsparts/verbs.py::args.cmd == retract`*

*Observed 2026-10-20 (python-dev)*
