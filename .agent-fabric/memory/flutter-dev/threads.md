---
role: "flutter-dev"
class: threads
topic: "evidence-reporter-timer-flake"
description: "gzapp passenger boarding_evidence_reporter_test \"the timer ticks at the given interval\" is a real-clock test that fails under full-suite load"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "flutter-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - dd126b5c44e0e49d
---

## gzapp passenger boarding_evidence_reporter_test "the timer ticks at the given interval" is a real-clock test that fails under full-suite load

apps/passenger_flutter/test/features/journey/boarding_evidence_reporter_test.dart, test "the timer ticks at the given interval, and not after stop", runs a 40 ms real-clock timer and expects 2..5 ticks in 180 ms. On 2026-10-19 it got 1 tick once in a full `flutter test` run on develop-qzapp (1530 passed, 1 failed), and passed 5/5 when run alone. The branch under test did not touch the reporter. It is a load flake, not a regression. When it fails in a full run, rerun the file alone before blaming the change. Making it robust (a fake clock, or wider bounds) is still open.

*Observed 2026-10-19 (flutter-dev)*
