---
role: "python-dev"
class: workflow
topic: "journal-off-send-w17-lessons"
description: "j133 W17 #623 - a presence rule change turns neighbouring tests stale; vacuity fix can expose a real gap; re-review brief must be pasted from the file"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 65f79722ec3f8ba7
---

## j133 W17 #623 - a presence rule change turns neighbouring tests stale; vacuity fix can expose a real gap; re-review brief must be pasted from the file

j133 (#623): a presence rule change (carrier-only asks only the agentd) made the gate-2 test stale; ask the coordinator which side is right before editing. A suite reading the account's live transport-mode file needs its own AGENT_FABRIC_STATE_DIR. Making a vacuous check able to fail (F5) exposed a real gap (D6 re-served record shown): pin it as a named limit and report, never hide. The security-boundary arm (presence.py, under 8 work) accepts the basis phrase "the owner's word" when the owner said "arm N". Re-review: request needs card_base and the round-1 range; paste the brief file verbatim (I mistyped one line).

**Why:** each cost a round-trip. **How to apply:** see above before the next arm of a control/ change.

*Observed 2026-11-16 (python-dev)*
