---
role: "db-admin"
class: workflow
topic: "delivered-jobs-close-on-merge"
description: "A job delivered as a for/ branch or a memory stays \"delivered\" until closed with fabric-jobs done; check it when the caller's PR merges or the drain lands"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "db-admin"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 443d125ad22c9b2d
---

## A job delivered as a for/ branch or a memory stays "delivered" until closed with fabric-jobs done; check it when the caller's PR merges or the drain lands

A job whose artifact is a `for/` branch supplied to another role's PR, or a
memory awaiting a drain, ends at `delivered`, not `done`: nothing closes it
when the PR merges or the drain lands. On 2026-10-18 fabric-coordinator
found seven such jobs a week stale (j8–j17; gzapp#1092 had merged on
2026-10-11 with both supplied commits, 729c13237 and 75bf95221).

**Why:** a stale `delivered` job reads as open work in every sweep of the
fleet and costs the coordinator a REQUEST to clear it.

**How to apply:** at each session start, for every `delivered` job, check
the caller's PR (`gh pr view <n> --json state,commits`) or the slice on
origin/main; close it with `fabric-jobs done <id>` once it lands, and
drop a duplicate job that was opened for the same REQUEST.

*Anchors: `tools/fabric/jobsparts/base.py::OPEN`*

*Observed 2026-10-18 (db-admin)*
