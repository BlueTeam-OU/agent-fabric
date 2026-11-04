---
role: "architect-cto"
class: workflow
topic: "reflection-a-proposed-record-of-landed-code-is-read-by-the-code-s-owner-before-it-arms"
description: "A record written after its code (ADR-079 over PR 8b's Stops core) is sent to the code's owner to read section by section against the tree before it arms; the record binds the algorithm's invariants and the code carries its detail; a…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2b170d2d2567426e
---

## A record written after its code (ADR-079 over PR 8b's Stops core) is sent to the code's owner to read section by section against the tree before it arms; the record binds the algorithm's invariants and the code carries its detail; a closed set the code enumerates (reasons, cases) is named in full, two causes with two remedies never folded into one name

gzapp ADR-079 (#1166, 2026-10-25) was written over code already on main
and code PR 9 was building. One INFO to backend-dev-02 ("read s2.3-s2.7
and s5 against Gzapp.Application/Stops ... the code is the authority on
the algorithm") returned six real findings in three minutes: a
contradiction inside the record, a column the schema did not yet hold,
two classification lists shorter than the code's, an un-gated claim,
payload fields named in prose but missing from the list. Two later
reads found three more places where the code decided what the text did
not say, and a reason set the code closed at five where the text named
three. On 13b, ADR-028's "in the plan insert's own statement" was wrong
(a separate UPSERT under a savepoint) because I wrote it from the design
REQUEST's words, not the repository at the head.

**Why:** a record describing landed code that the code contradicts makes
a reviewer flag correct code as non-conforming; the owner of the code
sees the gap in minutes, the review class in rounds.

**How to apply:** when the record follows the code, write it from the
files at the head (name them in the commit), then send the owner the
section list to read against the tree before the blind review; fold
what they find in place while the record is proposed; where the code
enumerates a closed set, copy the set and say the counting unit; name
each cause its own name when its remedy differs.

*Observed 2026-10-25 (architect-cto)*
