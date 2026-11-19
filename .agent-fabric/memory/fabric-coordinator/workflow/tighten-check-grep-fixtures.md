---
role: "fabric-coordinator"
class: workflow
topic: "tighten-check-grep-fixtures"
description: before tightening adr.py check (or any guard), grep tests/fixtures and the hook suites for what the new rule refuses — they copy or ship records that the old rule let through
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 38714eb2ea5b0ab8
---

## before tightening adr.py check (or any guard), grep tests/fixtures and the hook suites for what the new rule refuses — they copy or ship records that the old rule let through

j707 (2026-11-11): two `adr.py check` tightenings on #551 (cdc970ce: every DIGEST line counts, a
line before the first bullet is a finding; amendment bullets in date order) passed `test_adr.py`
and then broke two other suites. `tests/fixtures/adr-mini/docs/adr/DIGEST.md` had unbulleted
entries ("A fixture entry."), refused by the pre-commit hook in `test_githooks_cli.py` and
`test_githook_pre_commit.py`; and `test_adr.py`'s `amend()` back-dated amendments (2026-09-28)
onto a fixture that copies the real records, so they fell out of date order (moved to 2099).

**Why:** a guard's own test file is not its only reader — every hook suite runs it over a fixture.

**How to apply:** before committing a stricter check, run it over `tests/fixtures/**` and grep the
suites that call the hook (`grep -rln 'adr' tests/test_githook*`); fix the fixture in the same PR.
Related: [[tests-and-suite]].

*References: tests-and-suite*

*Anchors: `tools/fabric/adr.py::a line before its first bullet`, `tests/fixtures/adr-mini/docs/adr/DIGEST.md::- A fixture entry.`*

*Observed 2026-11-10 (fabric-coordinator)*
