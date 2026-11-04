---
role: "fabric-coordinator"
class: workflow
topic: "digest-entry-over-250-words"
description: an amendment bullet pushes a DIGEST entry over 250 words — what adr.py check allows when trimming it
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ebda0bf2eb27e978
---

## an amendment bullet pushes a DIGEST entry over 250 words — what adr.py check allows when trimming it

`tools/fabric/adr.py check` counts a DIGEST entry by whitespace split, heading included, so every amendment
bullet costs four tokens before its text (`-`, `A`, the date, `—`). It also requires one bullet per history
amendment, in order, so merging same-date bullets is refused ("bullets … are not its history").
`fabric-adr lookup` matches case-insensitive substrings of the whole block, so a keyword that is a substring
of other text there can go; ADR-029 had none.

What freed the words on 87e5c7bc (j463, ADR-029 at 260): a bare bullet with no section ref (`- A 2026-10-31 —
roles.`), `(r3, r12)` → `(r3/r12)`, articles dropped, and a keyword (`busy`) that the `busy flocks` bullet
already contains. Then `adr.py index --write`, `check`, and after committing `range-check` (see
[[adr-range-check-before-push]], [[digest-trim-keeps-lookups]]).

j478 (ADR-037 at 259, 8fbe6a9c on #437): seven bullets shortened by one or two words each (articles, a
`fabric-jobs` already named elsewhere). A §2–§8 mention of an amendment must be the literal `(A YYYY-MM-DD)` on
one line (`UNDATED_SPANS`): `(… j75; A 2026-10-31)` or a span broken by the line wrap reads as a dated §5.

*References: adr-range-check-before-push, digest-trim-keeps-lookups*

*Anchors: `tools/fabric/adr.py::DIGEST_ENTRY_WORDS`, `tools/fabric/adr.py::cmd_lookup`, `tools/fabric/adr.py::UNDATED_SPANS`*

*Observed 2026-10-31 (fabric-coordinator)*
