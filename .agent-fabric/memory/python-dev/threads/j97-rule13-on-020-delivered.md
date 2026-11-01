---
role: "python-dev"
class: threads
topic: "j97-rule13-on-020-delivered"
description: "j97 — rule 13 rerun on InterWeave 0.2.0 passed; J92_PEER patch folded by coordinator (#417); traps for the next rerun"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 388662da6aa7b126
---

## j97 — rule 13 rerun on InterWeave 0.2.0 passed; J92_PEER patch folded by coordinator (#417); traps for the next rerun

j97 (2026-10-28): rule 13 on 0.2.0 green, run 1793184500000, python-dev-02 + python-dev-03; result sent by REPLY, coordinator writes the record. Patch 22c800f4 (J92_PEER, tests/live_interweave_two_accounts.py) went as for/user/j401-rule-13-peer; coordinator's static suite then failed ruff F841 (`doc` dead at the old line 241): I ran lint.py but not `ruff check` on the file — run ruff on touched files before pushing (j98 fixes it).

**Traps for a rerun:** since the install the units (interweave-daemon@/interweave-client@gzcoord) already run with the full 30-row roster, so skip serve/stop (serve refuses their config); set J92_PEER (the roster no longer has two rows). A used J92_RUN is refused by the sender: after a failed attempt take a new number. A second account that is busy costs hours: message it first and make sure it started, and its "starting" notice must have a body (gzcoord-send refuses an empty one). The hook blocks commit/push once the job left active: do fixes inside the fresh session of the queued job.

**Why:** owner put ADR-064 steps at max priority. See [[j92-rule13-carrier-live-check-state]].
**How to apply:** repeat = same script, new J92_RUN, J92_PEER, ruff clean.

*References: j92-rule13-carrier-live-check-state*

*Observed 2026-10-28 (python-dev)*
