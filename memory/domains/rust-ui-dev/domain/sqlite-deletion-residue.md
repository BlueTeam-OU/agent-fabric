---
role: "rust-ui-dev"
class: domain
topic: "sqlite-deletion-residue"
description: "Proving deletion in a SQLite local store -- where released plaintext survives (freed cells, WAL), the pragmas that remove it, and the byte-search test with a live control"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - dffe4fba0e2fdbfb
---

## Proving deletion in a SQLite local store -- where released plaintext survives (freed cells, WAL), the pragmas that remove it, and the byte-search test with a live control

A SQLite store in WAL mode without secure_delete does not delete content from its files:
- a row deleted after it reached the main file leaves its plaintext in the freed cell of
  the main file, still there after a clean close (the WAL is gone by then);
- a row deleted before checkpoint sits in the WAL while the store is open.
Measured on a phone and on a desktop host with the same bundled SQLite.

To make "removed" true: PRAGMA secure_delete=ON on every connection, and
wal_checkpoint(TRUNCATE) after each release (or within a bound the store enforces), at
open of an existing store and at close; a checkpoint blocked by a reader is an error, not
a silent pass. A store written before the change needs a one-time rewrite (VACUUM).

Proof: byte-search BOTH files for a long test-only marker after release-then-close,
release-while-open past the bound, and crash-then-reopen, with a KEPT message's marker as
the control that shows the search is live; mutate each mechanism off to see its test fail.

Trap from the measurement itself: a harness that printed twelve readings through a
positional format list swapped two labels, and the first report named the wrong file.
Print measurements with named fields and pin the labels with a test.

*Observed 2026-10-15 (rust-ui-dev)*
