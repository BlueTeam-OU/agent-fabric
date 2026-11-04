---
role: "python-dev"
class: solution
topic: "fabric-drift-design-j138"
description: "fabric-drift (#333, j138) design: retired vs missing, bounded read, stale semantics, op caching; what a record-vs-tree check must not trust"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 95ec068621b6e85a
---

## fabric-drift (#333, j138) design: retired vs missing, bounded read, stale semantics, op caching; what a record-vs-tree check must not trust

`tools/fabric/account_drift.py` + `bin/fabric-drift` + control op `drift` (merged #333, 2026-10-20).
- The record (`fabric-written.json`) only grows: `fabric_writes` has no forget and reads an unreadable record as empty. So the check reads it strictly (exit 2) and an absent file is `missing` only when `bootstrap --dry-run` would write it; otherwise `retired` (counted, not listed). Without that split any account that changed role reports drift for good (review F1).
- A recorded path can be a FIFO or a link to /dev/zero: stat-check, open O_NONBLOCK, fstat the descriptor, chunked hash, 64 MiB cap. Each size bound alone is redundant with the other; the fstat check is race-only and cannot be pinned by a test.
- `stale` = a dry-run "+ x (would write|would link)" line no edited/missing/unreadable path explains (equality, or path + space; tails " -> " and " fabric user settings" only). `.claude.json` lines are dropped on purpose.
- Op: operator-only unsigned read, run beside the loop, cached 60 s; reply capped at 100 findings, no hash or content.
- Run from a worktree, every link reports stale (bootstrap links to the checkout it runs from).

**Why:** the first design read every absent path as missing and had an unbounded read; both found by blind review. **How to apply:** any "record vs tree" check — separate what the tool removed itself from what it lost, and bound every read of a path the account owns. See [[bounded-subprocess-three-seams]], [[child-in-own-session-needs-interrupt-kill]].

*References: bounded-subprocess-three-seams, child-in-own-session-needs-interrupt-kill*

*Observed 2026-10-20 (python-dev)*
