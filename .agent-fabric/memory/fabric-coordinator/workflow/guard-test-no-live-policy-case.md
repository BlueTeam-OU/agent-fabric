---
role: "fabric-coordinator"
class: workflow
topic: "guard-test-no-live-policy-case"
description: "A guard's test file must not judge the live tree against a policies/*.json — stripped-nightly removes them; corpus lint is the tree's check"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8ecfded6d3c44149
---

## A guard's test file must not judge the live tree against a policies/*.json — stripped-nightly removes them; corpus lint is the tree's check

tests/stripped_run.py strips every policies/*.json (ADR-045 rule 3). A test case that runs a guard over the checkout with its live allowlist (tests/test_state_writes.py case_tree_is_clean, landed in ffa116f2 on 2026-11-03) goes red there: every admitted module becomes a finding. Removed in 1d208658 (j608, rides #488): the corpus lint in tests/run.py already runs the same function on the tree.

**Why:** stripped-nightly went red 2026-11-04 (run 41816943040) one day after the guard landed; nobody runs a stripped copy before merge.

**How to apply:** when adding a guard, keep its test file on fixtures only; before merge run `python3 tests/stripped_run.py . tests/test_<guard>.py`. A case that must read the operator's data goes in STRIPPED_RED (tests/test_tests_read_fixtures.py), whole file. Related: [[checks-need-a-control]].

*References: checks-need-a-control*

*Anchors: `tests/instance_fixtures.py::def strip_instance`, `tests/test_tests_read_fixtures.py::STRIPPED_RED`*

*Observed 2026-11-04 (fabric-coordinator)*
