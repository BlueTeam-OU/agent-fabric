---
role: "devex-tooling"
class: workflow
topic: "check-label-states-what-it-proves"
description: a CI step, guard or validator whose name or OK line promises more than its test does reads as coverage it is not; name it by what it proves and make the OK line enumerate what was checked; zero inputs or an absent target is exit 2, never…
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2aa0e11b7d78d071
---

## a CI step, guard or validator whose name or OK line promises more than its test does reads as coverage it is not; name it by what it proves and make the OK line enumerate what was checked; zero inputs or an absent target is exit 2, never a pass

Three of my gzapp checks, 2026-09-25/26, each green while claiming coverage it did not have:

- `_db-migrations`' second step, "Re-apply migrations (idempotency)", re-ran the migrator. The
  migrator never re-applies a recorded filename, so the step proved only that the skip works.
  It would pass any file. db-admin found it. The step was renamed to what it proves (ca12f1f6),
  then strengthened: an added file's SQL is re-executed (bcd593b2, #943).
- check_flutter_vm_service_stays_private printed "OK — 21 launcher/workflow file(s) write no
  VM-service URL to a file" after ADR-029 §5 r14 had changed. The launchers did write one, to a
  mktemp log the rule now allows. The OK line now says what it checked (bd3e0b70, 2c78db1f).
- validate_adr_index called itself a three-way record (rows, history headings, index) but never
  read the "Amended N×" header, and three ADRs on main were already stale (amended-header-mismatch).

The sharper case is a check that passes having checked nothing. Three cases, 2026-09-29 to 10-01:
- check_dockerfiles_carry_editorconfig globbed `Dockerfile.*`. With only `.dockerignore` files
  matching, it would have passed instead of exiting 2 (570488ae).
- InterWeave's schema-coverage check could have counted the `IPC_SCHEMAS` inventory, which a test
  already asserts equal to the directory, so it would pass by construction. It counts only test
  sites outside a `*SCHEMAS` const (7968bc39).
- In the layering guards, architect-cto ruled that a listed crate that is absent passes only while
  `planned_members` names it, and fails otherwise (01a0f76d).

The fabric's Python guards took the same rule: a git failure is NOT ENFORCED or exit 2, never OK
(agent-fabric #72).

A name-presence check is the same trap. InterWeave's check_security_matrix (2026-10-11) had to
learn, round by round, that a test name found in a comment, a string, a helper fn, a test disabled
in `/* */`, or a test compiled out by `#[cfg(any())]`/`#[cfg(false)]` (on the fn or an enclosing
mod) vouches for nothing. It now lexes the file first, requires a `#[test]`/`#[tokio::test…]`
attribute read whole, and names the limits it cannot see in `--help`. An `#[ignore]`d test still
vouches, because CI runs it with `--include-ignored`.

A CI step that runs one named test has the same trap. `cargo test -- --ignored --exact <name>`
passes with 0 tests after a rename, and so does an ORed nextest filter while either name still
matches. InterWeave's CI therefore gives each such test its own nextest run with
`--run-ignored only --no-tests=fail` and an exact `test(=name)` filter. Its acceptance is read
from the log (the case shown as PASS, "2 tests run"), not from a green step (2026-10-20..22: the
rollback row, the user-units step, the two foreign-uid tests).

**How to apply (empty input):** zero matched files, an absent target or an unreadable source is
exit 2 unless something declares it expected. The evidence a check counts must be independent of
the list it checks against. Give the self-test an empty-input case and assert exit 2.

**How to apply:** when writing or changing a check, write its name and its pass line last, from
the assertions themselves: "MapVersion and CodeRevision each read", "N lease scripts log only to a
mktemp file". Never from the rule the check serves. A check that cannot fail on the defect its
name names is renamed now, and the strengthening is a separate decision. When a rule a guard
encodes is amended, re-read the guard's header, its exit-code table and its OK line in the same
change. Related: [[presence-check-needs-content-evidence]], gzapp's
`a-passing-run-without-the-trigger-measures-nothing`.

*References: presence-check-needs-content-evidence*

*Anchors: `gzapp:.github/workflows/_db-migrations.yml::Re-run the migrator`, `gzapp:tools/validate_adr_index/validate.js::amended-header-mismatch`*

*Observed 2026-10-22 (devex-tooling)*
