---
role: "web-dev"
class: domain
topic: "vitest-coverage-withheld-on-failure"
description: measuring Vitest coverage on a loaded host — a run with any failed test prints no coverage report unless reportOnFailure is set
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2673d8a0c10d7db7
---

## measuring Vitest coverage on a loaded host — a run with any failed test prints no coverage report unless reportOnFailure is set

Vitest 5 (`@vitest/coverage-v8`) prints no coverage summary at all when any test fails, unless
`--coverage.reportOnFailure` is passed. On a contended host (load ~150 on 10 cores, 2026-10-19)
gzapp admin_web at full concurrency failed 32 tests, 22 of them timeouts, and printed no number;
at `--maxWorkers=3` it failed 2 and reported. Measure with
`--maxWorkers=3 --coverage.reportOnFailure --coverage.reporter=json-summary` and say in the report
which tests failed, because a failed test's lines count as uncovered and lower the number.

To prove a configured threshold is enforced without a full run, run one small test file under
`--coverage`: it must fail with "does not meet global threshold (N%)".

Seen on gzapi-org/gzapp#1137. Related: [[test-setup-must-separate-wrong-impl]].

*References: test-setup-must-separate-wrong-impl*

*Observed 2026-10-19 (web-dev)*
