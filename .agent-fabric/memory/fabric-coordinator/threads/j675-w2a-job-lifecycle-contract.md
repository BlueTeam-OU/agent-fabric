---
role: "fabric-coordinator"
class: threads
topic: "j675-w2a-job-lifecycle-contract"
description: "ADR-067 Wave 2 W2-A (job lifecycle owner) contracted to python-dev-04 on 2026-11-09; what comes back and what I owe on it"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 10cf6a5499efbfe8
---

## ADR-067 Wave 2 W2-A (job lifecycle owner) contracted to python-dev-04 on 2026-11-09; what comes back and what I owe on it

ADR-037 rule 14's pool-end rows landed on main before j675 started (b0c0f08c, 93c221cc, f839296b), so j675 reduced to the W2-A contract: REQUEST 01a1be8b-e3c2-758b-8ac0-fb2c149d2471 to python-dev-04 (2026-11-09), covering #512 F1-F11, the optional `claims` state-record field and both pool rows, and the ADR-067 checker.

**Why:** python-dev-04 wrote j100 (#512) and had no open job; the other three python-dev holders each had one active.

**How to apply:** python-dev-04 queued it as j101. The entry cannot go `pending` before its owner module is tracked (lint_rules/mechanisms.py asks a tracked owner path for pending), so it stays `planned` with waits_on python-dev-04/j101 (BlueTeam-OU/agent-fabric#520). Set `pending` once the owner lands. When its exceptions file arrives on `for/user/`, fold it, wire the checker into lint, the pre-commit hook and a tests/ case, and mark the entry `enforced` (as Wave 1: #515, #516). Over 16 work commits means a split at the pool rows (W2-A2), not one oversized PR.

*Observed 2026-11-09 (fabric-coordinator)*
