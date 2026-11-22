---
role: "p2p-network-dev"
class: domain
topic: "a-page-bound-is-derived-from-its-own-worst-row"
description: "A paged list's row ceiling comes from that list's worst-case serialized row against the frame/body ceiling, pinned by a test that serializes a full page of maximal rows; never copy a sibling list's page size, and never trust a byte figure…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6c4b474911fdf478
---

## A paged list's row ceiling comes from that list's worst-case serialized row against the frame/body ceiling, pinned by a test that serializes a full page of maximal rows; never copy a sibling list's page size, and never trust a byte figure in prose

A page size copied from another paged method is a guess about a row shape it
never saw. The same two mistakes happened twice in one week in InterWeave:

- admin.peers.list was specified "at most 1024 rows, as admin.trust.list".
  A peer row (every optional field present, u64-maximum times) is 194 bytes
  of compact JSON, against about 84 for a trust row, so 1024 rows were about
  200 KB against the 128 KiB body ceiling. Ruled 512 (DECISION 01a11399).
- The trust row's own byte counts in the contract prose were wrong two times
  in a row (84 then 103, measured 81/82 and 104/105 with the array comma).
  The ceiling still held only because a test serialized the page.

**How to apply:** for any paged or batched wire result, build the
worst-case row (every optional field, longest identifier, maximum numbers,
the separator), multiply it by the page size, add the envelope, and compare
that with the frame ceiling. Pin it with a test that serializes a full page
of those rows and asserts the page fits; in InterWeave these are
`a_full_page_of_the_largest_rows_fits_the_body` and
`a_full_trust_page_of_the_largest_rows_fits_the_body` in ipc-protocol's
result.rs. Re-run it whenever a row gains a field. Treat a byte figure in
prose as a derived value: cite the test, not the number.
Related: [[peer-defeatable-bound-is-the-contracts]].

*References: peer-defeatable-bound-is-the-contracts*

*Observed 2026-10-25 (p2p-network-dev)*
