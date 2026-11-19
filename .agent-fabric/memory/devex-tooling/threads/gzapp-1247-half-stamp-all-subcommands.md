---
role: "devex-tooling"
class: threads
topic: "gzapp-1247-half-stamp-all-subcommands"
description: "j324 design — flutter-run-leased half-stamp refusal should apply only to run/build (the subcommands it stamps); #1247 merged with it on every subcommand"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8094700701c2936e
---

## j324 design — flutter-run-leased half-stamp refusal should apply only to run/build (the subcommands it stamps); #1247 merged with it on every subcommand

gzapi-org/gzapp#1247 merged 2026-11-10 21:25Z (b15e9003) with my 654f59bb4: tools/mcp/flutter-run-leased.sh refuses
(exit 64) half an i18n baseline stamp for EVERY flutter subcommand (the check at ~line 245 is outside the
`run|build` test at ~256). flutter-dev-01's re-review flagged it (REPLY 01a1c747), untested either way.

Decision taken for j324 (owner said "take it", 2026-11-11): refuse only where the script stamps — run and build —
and pass every other subcommand through untouched. Reasons: the header says the stamp "covers a flutter run or
build handed here directly"; a `flutter test` exercising the unstamped/half-stamped isStamped path needs exactly a
half stamp; both callers on main (apps/{driver,passenger}_flutter/scripts/run-linux-mcp.sh) pass only `flutter run`.
`drive` also compiles an app but is not stamped either: say so, keep scope aligned, do not widen.

Tests in tools/mcp/test_flutter-run-leased.sh (the `half` helper ~line 500): add a case that `flutter test` with
VERSION alone passes through with argv unchanged and no stamp appended; keep the run/build refusals. Mutate:
moving the check back outside run/build must fail the new case. Job copy: ~/projects/gzapp-j324-flutter-run-leased-refuse-half-an,
own gzapp PR (nothing else in flight on tools/mcp/ on 2026-11-11). CI runs it via _ban-checks.yml:430.

*Observed 2026-11-11 (devex-tooling)*
