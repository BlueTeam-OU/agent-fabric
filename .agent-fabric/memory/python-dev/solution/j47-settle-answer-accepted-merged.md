---
role: "python-dev"
class: solution
topic: "j47-settle-answer-accepted-merged"
description: "settle.py's answer predicate (accepted + non-empty IN-REPLY-TO) merged in #277; what stays open for the coordinator"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - da6c48d9c605dcde
---

## settle.py's answer predicate (accepted + non-empty IN-REPLY-TO) merged in #277; what stays open for the coordinator

#277 merged 2026-10-15 (3abaf62c, 1 work, 1 fix, armed on the owner's word). `tools/fabric/jobsparts/settle.py` `_ANSWERS` = outbound, `state='accepted'`, non-blank `in_reply_to`; shared by `replied()` and `owed_replies()`. Failed, pending and empty-header sends answer nothing. Test helper `World.journal` takes "out" (accepted), "out-failed", "out-pending"; a bare pending row is no longer an answer.

**Open, not mine:** `policies/agent-jobs/SKILL.md` lines ~79-83 (REQUEST/QUESTION only, accepted, non-empty IN-REPLY-TO); `blockers.check_request` clears an `--on-request` blocker only on an inbound REPLY, not a DECISION; one P3 carried: jobs.py docstring does not say the window is the earlier of job and session start, nor that an undated row is owed.

**Why:** the review of #274 (594deba5) found these as pre-existing/P3. **How to apply:** a re-review of a fix range needs `card_base:` (the first round's base) in the request yaml, because the fix base is not on main. Push disarms an armed PR, so a lone P3 after arming is carried and named, not fixed.

*Anchors: `tools/fabric/jobsparts/settle.py::_ANSWERS`*

*Observed 2026-10-16 (python-dev)*
