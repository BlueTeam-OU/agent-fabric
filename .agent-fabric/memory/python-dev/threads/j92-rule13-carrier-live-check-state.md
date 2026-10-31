---
role: "python-dev"
class: threads
topic: "j92-rule13-carrier-live-check-state"
description: "j92 — ADR-064 rule 13 carrier half delivered and merged (#382): what ran, traps for a rerun"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a6e3148bbab6495f
---

## j92 — ADR-064 rule 13 carrier half delivered and merged (#382): what ran, traps for a rerun

j92 done: PR #382 merged 2026-10-25 (6 work, 3 fix). tests/live_interweave_two_accounts.py runs the INSTALLED pinned programs (~/.local/bin, digest-checked), the account's real gzcoord profile and the roster rows on main; phases check|serve|exchange|portcheck|stop; the page docs/live-checks/2026-10-25-interweave-two-accounts.md was committed by the coordinator (outside my entry: send it as a world-readable file + sha256 in a HANDOFF, rm the file after).

**Traps for a rerun:** J92_RUN (ms epoch, same for both accounts) must be new; the sender refuses a number whose own ids are in its outbox. Both accounts' control port is own roster port + 90 (a shared control port collided). Run portcheck one account at a time. A review brief goes to the code-review agent by file path (Read it) when it is 40 KB; fabric-review needs repository = the worktree path. Carried P3s: share dir owner unchecked, old-format state.json crashes stop, pre-invocation arrivals can satisfy the receive check.

**Why:** owner put ADR-064 steps at maximum priority 2026-10-25. See [[j90-carrier-client-unit-pr373]].
**How to apply:** a repeat of rule 13 (e.g. after a pin move) is the same script with a new J92_RUN and two logins.

*References: j90-carrier-client-unit-pr373*

*Observed 2026-10-25 (python-dev)*
