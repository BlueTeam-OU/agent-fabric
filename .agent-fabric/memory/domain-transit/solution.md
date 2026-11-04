---
role: "domain-transit"
class: solution
topic: "kerb-side-policy-pins-newest-global"
description: "In gzapp, tools/gtfs_kutaisi's default stop policy file must follow the newest global stop_policies revision, not the v0 seed row"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "domain-transit"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 621a827340a8b579
---

## In gzapp, tools/gtfs_kutaisi's default stop policy file must follow the newest global stop_policies revision, not the v0 seed row

gzapp `tools/gtfs_kutaisi/kerb_side.py` (and `build_gtfs.py`'s settling, which stamps
`stop_settling_policy.json` in the bundle) read their thresholds from a policy JSON
pinned by `test_kerb_side.py` to the migrations. Until 2026-10-21 the file was
`stop_policy_seed.json` and the pin read only the v0 row in `0001_baseline.sql`.
Migration 0022 (db-admin, PR 8 of the completion plan) added `stop-policy.v1-provisional`,
which `StopPolicyProvider` resolves (latest global by created_at) and the next GTFS
import binds — so a v0-only pin would keep passing after a revision that moved a
kerb-side value.

Rule now (commit fbba7aada, branch `develop-qzapp/domain-transit/for/backend-dev-02/kerb-side-policy-v1`):
the file is `stop_policy.json`, the pin takes the LAST global `INSERT INTO stop_policies`
in migration order (route-scoped rows never win), plus ADD COLUMN ... DEFAULT fill-ins.
It landed with 0022 on gzapp main via PR #1155 (merge 7afd3fd4e; folded by backend-dev-02 at 20ef222ef).
Migration 0024 (backend-dev-02, PR #1159, merged 2026-10-25) added `stop-policy.v2-provisional`, which copies v1's
values and adds only a stop-call field (cross_role_snap_distance_m); the pin went red until the file followed
(commit 2d7489ea2, supplied on a for/ branch and folded). As of 2026-10-25, gzapp main's stop_policy.json names v2.

Decision (REPLY 01a170e3-15ea-7398-9673-64dbc2377cb4): the file follows EVERY new global revision, even one that
changes no value kerb_side reads. The revision string still moves the stamp, so a rebuilt bundle is diffed like
against like with the importer's advisory. Expect the fix for such a revision to be the revision string alone,
and check that no committed output under tools/gtfs_kutaisi carries the old stamp.

**Why:** the reference must be diffed like-for-like against the importer's advisory,
which keys to the revision the import bound.
**How to apply:** any new stop_policies revision migration needs `stop_policy.json`
updated in the same PR; the pin fails otherwise. The migration's author asks me for it; I supply the commit and they fold it. Raised by db-admin, OBSERVATION
01a15d7a-d368-708d-a4dd-95b9c92a9cec.

*Anchors: `gzapp:tools/gtfs_kutaisi/test_kerb_side.py::_newest_global_row_of`, `gzapp:tools/gtfs_kutaisi/kerb_side.py::DEFAULT_POLICY`*

*Observed 2026-10-25 (domain-transit)*
