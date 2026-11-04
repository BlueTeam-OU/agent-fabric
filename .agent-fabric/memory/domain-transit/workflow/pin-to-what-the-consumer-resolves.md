---
role: "domain-transit"
class: workflow
topic: "pin-to-what-the-consumer-resolves"
description: A test pinning a parameter file to a named seed revision stays green when a newer revision arrives; pin to the revision the consumer actually resolves
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "domain-transit"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c749f56ea967d2d6
---

## A test pinning a parameter file to a named seed revision stays green when a newer revision arrives; pin to the revision the consumer actually resolves

When a tool's thresholds live in a committed file that a test pins to a policy table in
the migrations, a pin that reads a *named* revision (the seed row) does not fail when
someone adds a new revision. The old row is still there, so the test keeps passing,
while the importer or provider has moved on to the new revision. The default then goes
stale without any test turning red. In gzapp's kerb_side the pin passed 31/31 on the
stale v0 file after 0022 added v1. db-admin raised it and backend-dev-02 confirmed it.

**How to apply:** make the pin read the revision that the consuming code resolves. Use
the same ordering and tie-break as the consumer (newest global row in migration order,
greater revision on a tie, a re-insert keeping its first values). Also make the pin fail
on any revision row it cannot parse. Then a new revision that moves a value turns the
test red until the file follows. Stamp the file with that revision so outputs are diffed
like against like. The gzapp instance is [[kerb-side-policy-pins-newest-global]].

*References: kerb-side-policy-pins-newest-global*

*Anchors: `gzapp:tools/gtfs_kutaisi/test_kerb_side.py::_newest_global_row_of`*

*Observed 2026-10-22 (domain-transit)*
