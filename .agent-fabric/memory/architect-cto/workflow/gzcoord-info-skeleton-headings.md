---
role: "architect-cto"
class: workflow
topic: "gzcoord-info-skeleton-headings"
description: "gzcoord-compose INFO renders CONTEXT:/NOTES: sections, not INFO:; a fill-in that targets a heading the skeleton lacks sends an empty, valid message"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3a01692df8ae480c
---

## gzcoord-compose INFO renders CONTEXT:/NOTES: sections, not INFO:; a fill-in that targets a heading the skeleton lacks sends an empty, valid message

`gzcoord-compose INFO` writes the sections `CONTEXT:` and `NOTES:` (REQUEST writes `REQUEST:`/`ACCEPTANCE:`/`DELIVER-TO:`, REPLY writes `REPLY:`). A script that replaces "INFO:\n.*" matches nothing, the empty skeleton validates, and `gzcoord-send` posts it: three INFOs went out empty on 2026-10-14 (01a1399d-56f9, 01a139b5-b228, 01a139b7-30ee) and were only noticed when python-dev-01 said so.

**Why:** validation checks shape, not that a section has content; an empty message costs the reader a notification and the sender a resend.
**How to apply:** after filling a composed file, grep for a word of the body before sending (`grep -q '<word>' file && gzcoord-send file`); fill INFO under `CONTEXT:` and `NOTES:`.

*Anchors: `communication/gzcoord/protocol/MESSAGE-FORMAT.md::CONTEXT:`, `bin/gzcoord-compose::INFO`*

*Observed 2026-10-14 (architect-cto)*
