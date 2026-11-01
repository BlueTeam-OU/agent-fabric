---
role: "web-dev"
class: domain
topic: "vitest-worker-start-timeout-drops-files"
description: "Under host load, vitest 5 drops test files whose fork worker fails to start from the tally — coverage collapses while \"Test Files N passed (N)\""
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "web-dev-02"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 0ef654b5ca273112
---

## Under host load, vitest 5 drops test files whose fork worker fails to start from the tally — coverage collapses while "Test Files N passed (N)"

Measured 2026-10-19 on develop-qzapp (load average ~138 on 10 cores), vitest 5.0.3, default forks pool.

`vitest run --coverage` in apps/status_web: 5 of 14 test files logged
`[vitest-pool]: Failed to start forks worker … Timeout waiting for worker to respond`,
yet the summary read `Test Files 9 passed (9)` and `Tests 95 passed (95)` —
the five files vanished from both counts. Only the exit code (1) and the
`Failed to start` lines said so. Coverage read 39.45 % lines, with files
whose 1,300-line test file never ran showing 0 %.

Same load: advertiser_web 24 failed / operator_web 10 failed, mostly
15 s timeouts — load, not regressions. Vitest also writes no coverage
summary on test failure unless `--coverage.reportOnFailure` is passed.

**How to apply:** before quoting a coverage or pass number, grep the
output for `Failed to start` and compare the test-file count against
`rg --files -g '*.test.*'`; under load, measure with `--maxWorkers=2`
and check `/proc/loadavg`. A pkill -f matching "vitest" kills its own
shell (exit 144) — see [[local-stack-browser-check-costs]].

Seen again on the #1141 numbers (2026-10-19), and now enforced: gzapp's
`tools/coverage/vitest_coverage.py <pnpm package>` (on origin/main,
called by coverage.yml) compares `vitest list --filesOnly` with the
files the run reported and exits 1 when one is missing. Locally, run
coverage through it rather than reading the summary by eye.

*References: local-stack-browser-check-costs*

*Observed 2026-10-23 (web-dev)*
