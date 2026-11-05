---
role: "fabric-coordinator"
class: solution
topic: "fence-exclusion-held-by-lint"
description: "when a contributor entry in policies/authority.json excludes a path, or a new trust file joins one, lint's CONTRIBUTOR_NEVER must hold it too"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 47f33e631941a036
---

## when a contributor entry in policies/authority.json excludes a path, or a new trust file joins one, lint's CONTRIBUTOR_NEVER must hold it too

A path a contributor entry's `excluding` keeps out is fenced only by that entry until `CONTRIBUTOR_NEVER`
(tools/fabric/lint.py) holds it: drop the exclusion and lint says nothing. j404 (PR #485, a42d9fe9 and 5cbb6c4f)
closed the gap for the carrier's roster.json/release.json and runtime/provisioning/github-host-keys(.fingerprints).
Check: every `excluding` entry is covered by some `_rule_covers(n, x)` over CONTRIBUTOR_NEVER (it now is).

A fence path that names a managed project (the carrier's) is spelled once as `CARRIER_FENCE` in
tools/fabric/lint_rules/docs.py, exempt from the project-name rule as exactly those strings, like `FABRIC_SELF`.
Never build it from the carrier package's `CARRIER_NAME`: that file sits in python-dev's entry and would move the fence.

Related: [[one-reader-has-second-callers]]

*References: one-reader-has-second-callers*

*Anchors: `tools/fabric/lint.py::CONTRIBUTOR_NEVER`, `tools/fabric/lint_rules/docs.py::CARRIER_FENCE`*

*Observed 2026-11-04 (fabric-coordinator)*
