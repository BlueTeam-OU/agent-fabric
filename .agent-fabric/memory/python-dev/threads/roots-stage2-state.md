---
role: "python-dev"
class: threads
topic: "roots-stage2-state"
description: "after #128 (merged 2026-10-09, d5a18cff): the tests-read-fixtures guard, strip_instance, and what is queued next (j63, j64)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2b61c4008f0fe4e6
---

## after #128 (merged 2026-10-09, d5a18cff): the tests-read-fixtures guard, strip_instance, and what is queued next (j63, j64)

#128 landed ADR-045 stage 2 for python-dev's 15 test files: tests/test_tests_read_fixtures.py (source
scan; ALLOWED = 17 not-yet-moved files + 2 deliberate live checks; UNSCANNABLE test_model_profile,
test_routing), tests/instance_fixtures.py (ADR_REGISTRY with fixture-proj, strip_instance),
tests/fixtures/gzcoord-operator (fixture-only-role). Lesson the review taught: a fixture must hold a
name the live data lacks, or a reader of the live file passes the case.
Queued: j63 results.py passes commit_class.Folds (coordinator request 01a11d6f; start after
develop-qzapp/user/feat/carried-after-125 merges); j64 wait_merged's no-required-checks text
([[gh-pr-checks-required-plain-text]]). Both go in one next PR.

*References: gh-pr-checks-required-plain-text*

*Observed 2026-10-08 (python-dev)*
