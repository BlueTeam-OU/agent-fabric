---
role: "python-dev"
class: solution
topic: "retry-sleep-capped-at-deadline"
description: "gzcoord-inbox retry sleep must be min(30, give-up bound left, deadline left); the refusing-relay test needs the give-up bound left at default"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6714cc8640641b73
---

## gzcoord-inbox retry sleep must be min(30, give-up bound left, deadline left); the refusing-relay test needs the give-up bound left at default

#287 (merged 94683984, j121): under --until-delivery the retry sleep in tools/fabric/gzcoord/inbox.py is capped at the time left to --deadline, so a refusing relay cannot overrun it. The test (tests/test_gzcoord_port.py, closed stub, --deadline 2) keeps GZCOORD_UNTIL_DELIVERY_DOWN_S at default so only the deadline can end it; removing the cap makes it time out.
**Why:** a between-arms deadline is overrun by any sleep not bounded by it ([[watch-deadline-seams]]).
**How to apply:** any new wait in the watch loop takes the deadline as a bound. Open, not mine: self-kill-guard.py:729-730 text omits the deadline end.

*References: watch-deadline-seams*

*Observed 2026-10-16 (python-dev)*
