---
role: "backend-dev"
class: domain
topic: "importer-counts-what-it-tolerates"
description: "An importer reading a producer's file (export, feed) — store your own reading of derived values, count every disagreement/clamp/skip in the report with a warning, refuse the file only for what the producer cannot have written"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "backend-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 996bcbe85890085f
---

## An importer reading a producer's file (export, feed) — store your own reading of derived values, count every disagreement/clamp/skip in the report with a warning, refuse the file only for what the producer cannot have written

The same value computed by two pieces of code will disagree on edge input: blank
versus whitespace, a non-ASCII space, overflow. One piece in SQL and one in C#, or two
arms of one CTE. An importer that refuses on any disagreement aborts a whole dataset
because of one row the producer was entitled to write. An importer that quietly takes
one side hides the drift.

The shape that held up in review:
- The importer **stores its own reading**: one shared helper, the same one the query
  side uses. It reads the producer's value only to **compare** with it.
- Every tolerance is **counted**: a disagreement, a value clamped to a bound, a row
  left out. The count goes into a report field, a warning when it is non-zero, and the
  CLI line. A tolerance that is not counted is a silent drop.
- The file is **refused** only for a row the producer cannot have written. A malformed
  line, or a value beyond the type, aborts deliberately, and the code says so.

**Why:** gzapp #844 F1 (2026-09-17). The export computed number_value with btrim into a
bigint. The importer read an int32 after .NET `Trim()`, which strips every Unicode
space. A ten-digit number or a house number led by an NBSP would abort the whole
import (01a0b07a, 01a0b082). The fix stored `HouseNumbers.LeadingInteger` and counted
`NumberValueDisagreements` (01a0b083). The re-review revert-tested it two ways
(01a0b0dd). The same week the GTFS span importer counted trips with no service where
it would otherwise have refused them (01a0b131), and counted its week clamp
(`ClampedServiceWindows`, 01a0b180) after a review found that the clamp was silent.
domain-transit's parent CTE chose names with a bare COALESCE while `base` guarded
blanks: "two expressions doing one job differently is the shape the bug took"
(01a0adfd).

**How to apply:** when a value crosses from a producer, write down which side's reading
is stored. Then write a test where the two readings disagree (leading whitespace,
NBSP, overflow) and assert the stored value *and* the count. Related:
[[read-the-counterpart-never-infer-its-shape]], [[committed-config-needs-its-own-test]].

*References: committed-config-needs-its-own-test, read-the-counterpart-never-infer-its-shape*

*Observed 2026-10-18 (backend-dev)*
