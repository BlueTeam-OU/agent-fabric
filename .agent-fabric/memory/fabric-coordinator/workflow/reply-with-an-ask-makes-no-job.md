---
role: "fabric-coordinator"
class: workflow
topic: "reply-with-an-ask-makes-no-job"
description: "A REPLY/INFO that asks me for something becomes no job and blocks no switch; fabric-jobs add --request <id> it on reading, or it is lost"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8e828ad32c4efca4
---

## A REPLY/INFO that asks me for something becomes no job and blocks no switch; fabric-jobs add --request <id> it on reading, or it is lost

Only a REQUEST is queued as a job on delivery (gzcoord/intake.py), and only an unanswered REQUEST/QUESTION with REPLY-EXPECTED: yes blocks `fabric-jobs switch` (jobsparts/settle.py owed_replies). An INFO, OBSERVATION or REPLY that carries an ask is neither.

On 2026-11-15, python-dev-02's j152 REPLY 01a1dc84 asked me for the ADR-029 §2 / ADR-064 rule 11 text #620 needed. It sat unread-for-action for five hours, until architect-cto chased on the owner's behalf (QUESTION 01a1dd9b).

**Why:** the intake reads message type, not content. A sender who puts an ask in a REPLY is following the conversation's shape, not the queue's.
**How to apply:** when a non-REQUEST message asks me to act, run `fabric-jobs add --request <MESSAGE-ID>` before anything else; it takes any message addressed to me. Proposed to the owner the same day: asks go as REQUEST (MESSAGE-FORMAT prose), and the receiver rule above in the agent-jobs skill. Related: [[gzcoord-messaging]].

*References: gzcoord-messaging*

*Anchors: `tools/fabric/gzcoord/intake.py::queue_received`, `tools/fabric/jobsparts/settle.py::owed_replies`*

*Observed 2026-11-15 (fabric-coordinator)*
