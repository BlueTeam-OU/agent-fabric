---
role: "fabric-coordinator"
class: workflow
topic: "carrier-entry-episodic-never"
description: "A journal change for the InterWeave carrier splits in two lanes — episodic.py is never-list (mine), tools/fabric/gzcoord/carrier/ is python-dev's entry"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ac67743b3557783d
---

## A journal change for the InterWeave carrier splits in two lanes — episodic.py is never-list (mine), tools/fabric/gzcoord/carrier/ is python-dev's entry

j389 (2026-10-28): recording the verified sender of an InterWeave copy touched both
tools/fabric/episodic.py (CONTRIBUTOR_NEVER in tools/fabric/lint.py — mine) and
carrier/engine.py + carrier/main.py (not on the never-list — python-dev's entry).
I landed the episodic half with its interface (record key `sender`, bc73f87a on #417's
branch) and sent the carrier wiring to python-dev-01 (REQUEST 01a182b4-409a), with
an acceptance test that runs the real journal_inbound against a real journal.

**Why:** the charter puts work inside an entry with its holder; [[data-and-reader-together]]
says a split contract needs a test that runs both real halves.
**How to apply:** for any carrier ↔ journal change, check `CONTRIBUTOR_NEVER` first,
fix the interface in my commit, then REQUEST the other half for a for/ branch.

*References: data-and-reader-together*

*Observed 2026-10-28 (fabric-coordinator)*
