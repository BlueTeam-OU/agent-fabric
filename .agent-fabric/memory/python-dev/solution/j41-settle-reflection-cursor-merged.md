---
role: "python-dev"
class: solution
topic: "j41-settle-reflection-cursor-merged"
description: "#274 merged (6619345f): settle.py reflection cursor, reply:<id> by own id, retract, any-answer; follow-up list and traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 941e256de7c39bf8
---

## #274 merged (6619345f): settle.py reflection cursor, reply:<id> by own id, retract, any-answer; follow-up list and traps

#274 (7 work, 2 fix) merged 2026-10-16 as 6619345f. settle.py: topic=reflection settles on the fabric-reflect cursor (done_at > job start); `replied()` and `owed_replies()` read any outbound row with IN-REPLY-TO (not only type REPLY); `fabric-jobs retract <id> <artifact>` removes one artifact in any state.

**Why:** a reflection pass lands no PR/sha; a DECISION answers a REQUEST; `gzcoord-send` prints only the reply's own id.

**How to apply:** follow-up PR (from the coordinator's review, not yet done): `IN-REPLY-TO:` empty header counts as an answer (use `coalesce(in_reply_to,'')<>''`); failed/pending sends count as answers (add a state filter); SKILL/jobs.py promise REPLY-EXPECTED on every type but owed_replies reads REQUEST/QUESTION only; blockers.py:98 clears a request blocker only on an inbound REPLY. Uncommitted round-3 fixes saved as a patch (undatable-start test must assert "so the fabric-reflect cursor cannot be dated"; jobs.py:108 help names an answer).

Traps met: `git push` has no credential helper in this account (use `-c credential.helper='!gh auth git-credential'`); full tests/run.sh gzcoord/launch/lease suites time out under host load and pass alone; below 8 work commits `fabric-pr arm` needs the phrase "the owner's word" in --basis, with the owner's actual word; a second review request must name `card_base` (the first round's base on main) and `previous_findings`.

*Anchors: `tools/fabric/jobsparts/settle.py::_reflected`, `tools/fabric/jobsparts/settle.py::replied`, `tools/fabric/jobsparts/verbs.py::retract`*

*Observed 2026-10-15 (python-dev)*
