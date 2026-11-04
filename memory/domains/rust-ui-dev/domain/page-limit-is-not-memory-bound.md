---
role: "rust-ui-dev"
class: domain
topic: "page-limit-is-not-memory-bound"
description: A client listing paged at the database but gathered into one collection is unbounded; bound what is held, take every count and preview from the store, never from the loaded window
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 024c3cfaf03710a0
---

## A client listing paged at the database but gathered into one collection is unbounded; bound what is held, take every count and preview from the store, never from the loaded window

An owner's review of InterWeave's client (2026-10-27) found the start-up listing paged correctly
in SQLite (64 rows / 1 MiB a page) and then extended every page into one Vec: page limits bound
one query, not the listing's memory, the bytes decoded at start or the update handed to the view.
A peer's backlog (20,000 unread x 49 KiB) could OOM the app before it drew; per-row derived work
(a card's standing recomputed against every contact) made it O(K x C). A later "session cap"
applied after the whole listing was built bounds nothing.

What the fix settled, as rules that transfer:
- Bound what is HELD, per unit the person sees (per conversation), never one global budget: a
  global budget can drop a whole conversation from the list while its badge still counts it — a
  count the person cannot find.
- Every count, preview and badge comes from the store (indexed counts, a per-conversation
  summary), never from the rows loaded; the list of conversations stays complete. Two clients over
  one store must print the same count, or one of them is a second truth.
- A sender-chosen key (a peer-asserted endpoint label) can multiply units; bound how many such
  units one sender may create, counted over durable store state, not a memory set.
- Precompute what a per-row comparison needs as a derived, versioned column recomputed at open
  when the derivation changes, so start-up decodes no payload.
- Releasing held rows never loses them: they come back at the edge they left by.

**How to apply:** for any start-up or list read, ask what bounds the bytes held after the last
page, and what the person sees at the edge; write a full-size #[ignore] run (tens of thousands of
rows) beside the unit tests.

*Observed 2026-10-31 (rust-ui-dev)*
