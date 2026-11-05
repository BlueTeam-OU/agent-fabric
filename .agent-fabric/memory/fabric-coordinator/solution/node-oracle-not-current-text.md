---
role: "fabric-coordinator"
class: solution
topic: "node-oracle-not-current-text"
description: "a tests/fixtures/node-oracle-*.json answer holds what the deleted Node said, never what Python must say now"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8f3ca8c8ee50ee78
---

## a tests/fixtures/node-oracle-*.json answer holds what the deleted Node said, never what Python must say now

The node-oracle fixtures (tests/node_oracle.py) freeze the deleted Node control
plane's answers (a20b4159). They are evidence of past wire behaviour: keep the
fixture as the Node answered, and keep comparing refused-versus-accepted, but a
human-facing text that the rule has outgrown is changed in Python and mapped in
the test with a comment. Decided 2026-11-04 for jobs-add's project refusal after
#377 widened the registry-id grammar to dots (j405, REQUEST 01a1a85a-4677 to
python-dev-04). Related: [[fix-a-claim-everywhere-it-is-made]].

*References: fix-a-claim-everywhere-it-is-made*

*Anchors: `tests/node_oracle.py::Oracle`, `tools/fabric/control/jobs.py::project is a registry id`*

*Observed 2026-11-04 (fabric-coordinator)*
