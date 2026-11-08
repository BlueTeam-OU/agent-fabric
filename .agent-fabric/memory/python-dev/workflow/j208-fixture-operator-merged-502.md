---
role: "python-dev"
class: workflow
topic: "j208-fixture-operator-merged-502"
description: "j208 (#502) gave merge_target_cases t1-t9 a fixture operator; the acceptance \"fails on main without a registry\" was not demonstrable"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9cafe7de44e78c99
---

## j208 (#502) gave merge_target_cases t1-t9 a fixture operator; the acceptance "fails on main without a registry" was not demonstrable

#502 merged 2026-11-07 on the owner's word ("open and arm"), 1 work commit, F1 (P3) deferred.
The earlier cases of tests/test_memory_write_check.py take their project from the binding,
so they passed with the registry absent, empty, or in stripped_run.py's copy: the request's
"fails on main" check could not be shown. Check a claimed hole with a counterfactual before
building the fix, and say in the PR body when the counterfactual does not fail.

**Why:** the review class proved by pointing the operator at a nonexistent dir that the fixture decides nothing.
**How to apply:** for a "reads the live registry" request, first run the old file with the registry emptied; if it stays green, report that before committing.
A full-suite red in test_control_agentd under load passed alone (55 tests, OK) while a review and CI ran concurrently.

*Observed 2026-11-07 (python-dev)*
