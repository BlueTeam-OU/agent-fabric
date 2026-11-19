---
role: "python-dev"
class: workflow
topic: "j147-rule13-0-3-0-and-594-review-r1"
description: "j147 Rule 13 on InterWeave 0.3.0 passed (REPLY sent); PR 594 round-1 review findings F1 P2 + two P3, not yet posted; job-guard trap"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 49aa15a0945d5444
---

## j147 Rule 13 on InterWeave 0.3.0 passed (REPLY sent); PR 594 round-1 review findings F1 P2 + two P3, not yet posted; job-guard trap

j147: check, exchange, portcheck all exit 0 on 0.3.0+c0bbe40a9bec; REPLY 01a1d7ca-e0b2-707d-8c4d-9ef6f880486a sent. No fabric-ctl command exists for the control link's own check (ADR-029 rule 18), so it went unrun and said so.

PR 594 (j146, head d19d24c4, 2 work + 1 fix) round-1 review, blind, claude class, not yet posted:
- F1 P2 control_link.py:735 — the 600 s hold cap is checked only after send_to returns, so a silent child holds the restart for the whole send budget; cap send_to at held_until or use a Timer cancelled in the finally, and add a test whose child never sends outbound.
- F2 P3 control_link.py:741 — past the cap the "released" log line repeats every 0.5 s; latch it, and log only when a hold was really released.
- F3 P3 tests/test_control_dual.py:192 — the test copies the hold and lacks the pending-leave check; move hold_for_ctl to a module-level function both use.
The report text is lost with the session (the hand-back is not in the subagent transcript): re-review at the head, do not try to recover it.

**Why:** the PreToolUse hook refuses a post-review once the session has worked a job that left active and none is active (ADR-037 rule 3); it also refuses any command that merely contains the two words unquoted.
**How to apply:** after j147 is done, `fabric-jobs switch` needs a memory change, then resume j146 in the fresh session: fix F1-F3, then a fresh review of the new head. Follows [[j146-ctl-restart-hold-pr594]].

*References: j146-ctl-restart-hold-pr594*

*Anchors: `tools/fabric/gzcoord/carrier/control_link.py::HOLD_MAX_S`*

*Observed 2026-11-14 (python-dev)*
