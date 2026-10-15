# ADR-021 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-15 — Rule 3 is Python only: the node suites are gone

The node suites are gone: tests/scratch.mjs was deleted in 2c9e8122 as
the last .mjs file, and no `*.test.mjs` is left for tests/static.sh to
check for an inline `mkdtempSync`. Rule 3 named both; it now keeps only
its Python half (a tool or suite registers the removal of its temporary
directory where it makes it). The test runner's own leak report moved
with it: tests/run.sh forwards to tests/run.py (#265), whose leak report
test_run.py holds, and the bash helper tests/leak-check.sh was retired
(#267); rule 2's parenthesis names run.py's report. Recorded as an
amendment, not an editorial edit, because rule 3 lost binding text,
including a check (review of #268, F4).
