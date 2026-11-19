---
role: "fabric-coordinator"
class: workflow
topic: "digest-entry-over-250-words"
description: "a DIGEST bullet over 60 words — adr.py check's budget is per bullet since 2026-11-09, no longer 250 words per entry"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d72fe544f472c57f
  - ebda0bf2eb27e978
---

## a DIGEST bullet over 60 words — adr.py check's budget is per bullet since 2026-11-09, no longer 250 words per entry

Since 2026-11-09 (the owner's direction; ADR-001 amended, commit ddc2c17d on PR #520, j693)
`tools/fabric/adr.py check` holds each DIGEST bullet, its continuation lines included, to
`DIGEST_BULLET_WORDS` (60), and an entry has no total. The 250-word entry total is gone: it made
every amendment of an often-amended record trim bullets it did not touch, and the trims dropped
lookup words (ADR-022's Monitor, ADR-029's resume, nearly ADR-032's metadata).

Still true: one bullet per history amendment, in order, two on one day included ("bullets … are not
its history"); a §2–§8 mention of an amendment is the literal `(A YYYY-MM-DD)` on one line
(`UNDATED_SPANS`), so `(A d1, A d2)` reads as a dated §; then `adr.py index --write`, `check`, and
after committing `range-check` ([[adr-range-check-before-push]]). A bullet over 60 is shortened in
itself (rule refs `§5 rules 1–3` → `§5 r1–3`, articles) or split into two rules; any word that
leaves the entry is looked up first ([[digest-trim-keeps-lookups]]).

*References: adr-range-check-before-push, digest-trim-keeps-lookups*

*Anchors: `tools/fabric/adr.py::DIGEST_BULLET_WORDS`, `tools/fabric/adr.py::cmd_lookup`, `tools/fabric/adr.py::UNDATED_SPANS`*

*Observed 2026-11-09 (fabric-coordinator)*
