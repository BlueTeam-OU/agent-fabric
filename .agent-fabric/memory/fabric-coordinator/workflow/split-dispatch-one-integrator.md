---
role: "fabric-coordinator"
class: workflow
topic: "split-dispatch-one-integrator"
description: "Owner 2026-10-22 \"pass work to python-devs\" — split one change across two holders with an agreed interface, one integrator PR"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 216b97d1d42da2f7
---

## Owner 2026-10-22 "pass work to python-devs" — split one change across two holders with an agreed interface, one integrator PR

When a contributor-entry change has two separable halves, the owner wants it spread across
holders, not queued on one: j349 went to python-dev-01 (--help per verb + `fabric-ctl --verbs`
interface, integrator, one PR) and python-dev-02 (completion.bash on a for/python-dev-01
branch, calling only `--verbs`). REQUESTs 01a163f9-d093 and 01a163f9-d24c.

**Why:** fleet throughput; the coordinator stays on the owner's priority (InterWeave).
**How to apply:** fix the interface between halves in both REQUESTs, name the integrator and
the for/ branch; the never-list piece (bootstrap.py install line) I supply onto the
integrator's branch. A job-on-job blocker is `job:<login>/j<n>`, not `job:j<n>`.

*Observed 2026-10-22 (fabric-coordinator)*
