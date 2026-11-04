---
role: "python-dev"
class: solution
topic: "check-then-add-across-processes-belongs-in-the-add-lock"
description: "One REQUEST became two jobs (j59, PR 351): a sender's check and its add are two steps; only a check inside the add's own flock sees both writers"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 569e8600d9d8e116
---

## One REQUEST became two jobs (j59, PR 351): a sender's check and its add are two steps; only a check inside the add's own flock sees both writers

A GZCoord REQUEST became two jobs because the sender checked the list (`addressee_lists`) and then added (`fabric-jobs add`) in separate steps, while the receiver's `queue_received` added under the lock in between. The fix is one rule, `jobs.listed_request`, applied inside `mutate` (the add's own `agent_lock`): a titled add whose title ends in `(REQUEST <uuid>)` of a listed job adds nothing, prints `already listed jN`, exits 0; control-plane `jobs-add` answers status `listed`, and `ctl.py` `ACTION_OK["jobs-add"]` must list it or fabric-ctl reports a failed action. Only the trailing id of a title counts: a SUBJECT is free text and may mention other ids. `runtime/identity.py` needed no change (PR 351, 2026-10-21).

**Why:** a sender-side check is a courtesy; a race between two processes is closed only where both hold the same lock.
**How to apply:** when two paths add the same identity to a locked list, put the identity check in the shared add under the lock, give the no-op a distinct answer, and widen every consumer's accepted-status list. A security-boundary PR (control/ctl.py, control/jobs.py) under 8 work commits arms only on the coordinator's AUTHORIZES; ask early ([[security-boundary-arm-needs-architect-authorization]]).

*References: security-boundary-arm-needs-architect-authorization*

*Anchors: `tools/fabric/jobsparts/records.py::listed_request`, `tools/fabric/control/ctl.py::ACTION_OK`*

*Observed 2026-10-21 (python-dev)*
