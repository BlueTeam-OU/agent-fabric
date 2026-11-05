---
role: "fabric-coordinator"
class: workflow
topic: "drain-anchor-repair-f1f2"
description: "a drain's new anchors must resolve where memory_check looks: prefix another project's path, repoint a literal moved behind a forwarder, hold a claim whose literal is gone"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1c6ac5b0b3555115
---

## a drain's new anchors must resolve where memory_check looks: prefix another project's path, repoint a literal moved behind a forwarder, hold a claim whose literal is gone

2026-11-01, #444 round 1 F1/F2 (j511): before committing a drain, diff memory_check --json
stale-hard anchors at the head against main's, per corpus (memory/domains needs --tree .).
Three repairs, applied to the bundles (~/drain/2026-10-31/fixed/fix_anchors.py + anchors-f1f2.json),
never to the written slices:
- another project's bare path in a claim bound for agent-fabric: `<registry id>:<path>::<literal>`;
  a project bundle's bare agent-fabric path gets `agent-fabric:`; a body `*Anchors:*` line that
  duplicates the prefixed field goes.
- literal moved behind a forwarder (bin/* → tools/fabric/*, tests/run.sh → run_python_suites.py):
  repoint, the claim unchanged.
- literal gone from a file that still exists: the fact may have changed — hold for the author.
A prefixed anchor reading "path is gone" may be a lagging local sibling checkout: check
`git -C ~/projects/<id> grep -F <literal> origin/HEAD -- <path>` before calling it stale.
Related: [[drain-multi-pass-procedure]], [[j279-drain-2026-10-31-state]].

*References: drain-multi-pass-procedure, j279-drain-2026-10-31-state*

*Anchors: `tools/fabric/memory_check.py::own_project_of`*

*Observed 2026-11-01 (fabric-coordinator)*
