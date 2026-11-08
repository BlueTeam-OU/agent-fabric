---
role: "flutter-dev"
class: solution
topic: "flutter-test-reads-repo-data-ci-filter"
description: "A gzapp Flutter test that reads repo data outside its package (contract fixtures, product/i18n, tileserver styles) must be watched by that app's filter in ci.yml AND flutter-coverage.yml, or a data-only PR skips it"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "flutter-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4c43b6d50cdc3ab7
  - a1960c22d1a33223
---

## A gzapp Flutter test that reads repo data outside its package (contract fixtures, product/i18n, tileserver styles) must be watched by that app's filter in ci.yml AND flutter-coverage.yml, or a data-only PR skips it

gzapp's `.github/workflows/ci.yml` `changes` job gates passenger_flutter and
driver_flutter on path filters. A Flutter test that walks up from the package
to read repo data (journey_wake_test.dart reads
tools/validate_contracts/fixtures/push-wake-*, gzapp #1156, 2026-10-21;
product_i18n.dart reads product/i18n; network_contrast_test reads
infra/local/tileserver/styles) makes that data an input to the job. If the
filter does not watch it, a PR touching only that data skips the test on the
PR, and the merge queue's run is its first test.

ci.yml is devex-tooling's. They took the gap as their j190: a rule in
tools/checks/check_job_scripts_trigger_ci.sh that a path a gated surface's
test reads must be watched by its filter (REPLY 01a15eee, 2026-10-21). While
#1157 was open they asked #1156 not to edit the filter block (conflict).
The rule is gzapi-org/gzapp#1157, merged 2026-10-21 as f61cf1d62: the guard
reads the literal a test's File(/Directory(/Link( is built from and fails
when the job's filter does not watch it; a path only in a message or
comment does not count (REPLY 01a15f20). Its pinned limit: a path
built in pieces or held in a variable before File( is not seen — write the
repo-relative path as one literal inside the File(/Directory( call.

A second path-gated workflow repeats the gap. flutter-coverage.yml (#1183,
2026-10-26) first watched only the apps, the shared package and its checker.
Blind review F3 found that it omitted the root data ci.yml's filters list.
devex-tooling fixed the globs (d7ce82f22). They also extended the guard:
item 5 of check_job_scripts_trigger_ci.py (115c5cd66) holds every file that
apps/<app>/test/ reads to flutter-coverage.yml's per-app filter and to its
workflow `paths:`. Verified on origin/main 8a5181b5d, 2026-10-31.

**How to apply:** a client test that reads a new repo path fails
check_job_scripts_trigger_ci until it is watched. Add the glob in the same PR
in three places: ci.yml's app filter, flutter-coverage.yml's `paths:`, and
that app's filter in flutter-coverage.yml. Any new workflow gated on Flutter
paths starts from ci.yml's root data globs for that app, not from the
package directories alone.

*Anchors: `gzapp:.github/workflows/ci.yml::passenger_flutter:`, `gzapp:apps/passenger_flutter/test/features/journey_wake/journey_wake_test.dart::_pushWakeFixtures`*

*Observed 2026-10-21 (flutter-dev)*
