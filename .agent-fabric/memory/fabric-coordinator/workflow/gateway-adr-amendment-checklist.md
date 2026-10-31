---
role: "fabric-coordinator"
class: workflow
topic: "gateway-adr-amendment-checklist"
description: "amending an agent-fabric-gateway ADR — the four places validate_adr.py checks, and a re-review brief whose base is off main needs card_base"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 095456db374fd504
  - 31aea4570f5d3d0f
---

## amending an agent-fabric-gateway ADR — the four places validate_adr.py checks, and a re-review brief whose base is off main needs card_base

An amendment to a gateway ADR (agent-fabric-gateway `architecture/adr/`) touches four places, and the gateway's
ADR checker, `validate_adr.py` (CI's step; anchored below) fails on any that disagree: the record's "Amended N×" line
and its Amendments table row, the record's amendment history file under `history/`, the `amendments` count in
`adr-index.json`, and the record's ADR-DIGEST.md entry (dates in parentheses). Gateway #64 needed the index bump
only after the validator said "3 index vs 4 history".

When a DIGEST parenthetical holds two dates, say which is which: one is when the evidence was measured, the
other when the amendment was made. A live-check record names a "gateway commit" only when a gateway was in the
request path.

`fabric-review brief` for a re-review whose base is the PR's previous head (not on origin/main) refuses until
the request carries `card_base: <first round's base>`.

cargo-deny advisories can turn a docs-only gateway PR red overnight; the lockfile is rust-services-dev's, so
send them a REQUEST, never bump it yourself.

*Anchors: `agent-fabric-gateway:tools/checks/validate_adr.py::check_amended_line`, `agent-fabric-gateway:tools/checks/validate_adr.py::amendment history file missing`, `tools/fabric/review_brief.py::card_base`*

*Observed 2026-10-23 (fabric-coordinator)*
