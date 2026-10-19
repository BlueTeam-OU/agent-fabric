---
role: "fabric-coordinator"
class: workflow
topic: "gateway-adr-amendment-checklist"
description: "amending an agent-fabric-gateway ADR — the four places validate_adr.py checks, and a re-review brief whose base is off main needs card_base"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 31aea4570f5d3d0f
---

## amending an agent-fabric-gateway ADR — the four places validate_adr.py checks, and a re-review brief whose base is off main needs card_base

An amendment to a gateway ADR (agent-fabric-gateway `architecture/adr/`) touches four places, and `python3 tools/checks/validate_adr.py` (CI's step) fails on any that disagree:
the record's "Amended N×" line and its Amendments table row, `history/ADR-NNN-amendments.md`, the `amendments` count in `adr-index.json`, and the record's ADR-DIGEST.md entry (dates in parentheses). Gateway #64 (j193) needed the index bump only after the validator said "3 index vs 4 history".

When a DIGEST parenthetical holds two dates, say which is which: one is when the evidence was measured, the other when the amendment was made. The #64 review F2 was a re-run dated with the amendment's date.

A live-check record names a "gateway commit" only when a gateway was in the request path. Checks 1-2 and the operation inventory run against a recorder or fake ("none in the path"), so ADR text must not give them the spike's commit as a gateway commit (#64 F1).

`fabric-review brief` for a re-review whose base is the PR's previous head (not on origin/main) refuses until the request carries `card_base: <first round's base>`.

Since 2026-10-15, cargo-deny advisories can turn a docs-only gateway PR red overnight: main's lockfile pinned rustls 0.23.45, and RUSTSEC-2026-0346..0349 arrived after main's last green run. The lockfile is rust-services-dev's; send them a REQUEST, never bump it yourself (REQUEST 01a13f35-9e18).

*Anchors: `agent-fabric-gateway/tools/checks/validate_adr.py::check_amended_line`, `tools/fabric/review_brief.py::card_base`*

*Observed 2026-10-15 (fabric-coordinator)*
