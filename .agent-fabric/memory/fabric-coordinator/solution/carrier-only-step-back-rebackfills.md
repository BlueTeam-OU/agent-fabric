---
role: "fabric-coordinator"
class: solution
topic: "carrier-only-step-back-rebackfills"
description: "Stepping an account back from carrier-only to carrier-record makes that period's outbound rows backfill candidates again; under 12 h posted late, older logged over-age"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b8d073807c9b3a5e
---

## Stepping an account back from carrier-only to carrier-record makes that period's outbound rows backfill candidates again; under 12 h posted late, older logged over-age

Since W9 (BlueTeam-OU/agent-fabric#611), `tools/fabric/gzcoord/backfill.py` is a no-op in
`carrier-only`: it leaves the journal's rows as they are and writes no
`gzcoord-backfill.jsonl` line. So when an account steps back to `carrier-record`, every
outbound row the carrier alone took during the `carrier-only` period is a candidate again.
A row younger than `MAX_AGE_S` (12 h) is posted to the relay hours late, and a relay reader
sees it as arriving at the step back. An older row is logged `over-age` and not posted.
Nothing is shown twice, because `dedup.admit` finds the message in each addressee's ledger.

The cutover plan's §6 "way back" says this since 139c5b2f (on #612, job j886). python-dev-01
raised it as a risk in INFO 01a1daa2. I chose to document it, not change the code.

**How to apply:** before a step back from `carrier-only`, tell the fleet that late relay rows
from that period are expected and are not new traffic. If late posts must not happen, the fix
is a mode-change marker that the backfill honours, which is python-dev's lane and needs a REQUEST.

*Anchors: `tools/fabric/gzcoord/backfill.py::MAX_AGE_S`, `docs/proposals/gzcoord-interweave-only-cutover.md::candidate again`*

*Observed 2026-11-14 (fabric-coordinator)*
