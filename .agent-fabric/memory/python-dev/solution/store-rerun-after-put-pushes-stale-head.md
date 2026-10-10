---
role: "python-dev"
class: solution
topic: "store-rerun-after-put-pushes-stale-head"
description: "Any secret-store path that pushes a head it built from the account's side (store push, seed-child's clone) must fast-forward to the remote first — the parent's puts make it behind"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 34aa674e5151b521
---

## Any secret-store path that pushes a head it built from the account's side (store push, seed-child's clone) must fast-forward to the remote first — the parent's puts make it behind

In the secret store (tools/fabric/secret_store.py) the parent writes into a
child's repository through its mirror, so the child's own store, and any
mirror rebuilt from the child's bundle, is routinely BEHIND the remote. A
push of that head is refused non-fast-forward. Two paths had it: seed-child's
clone path (mirror deleted by hand, item 7 of the coordinator's carried
audit, 2026-10-04) and `store push`, which store-enroll runs on a re-run
(found while testing item 3). Both now `fetch origin`, ff-merge
`refs/remotes/origin/main` when it exists (a new repository has no main),
then push; a diverged history still fails. Branch
develop-qzapp/python-dev-01/for/user/carried-audit, commits 51407c2, 605cbc0.

**Why:** the class is "a step built from one side's head, pushed to a remote
another writer also feeds" — fixing one instance left the other.
**How to apply:** any new push in secret_store/store_enroll gets the same
fetch + ff-only step; test it with a put the account has not taken
(tests/test_first_contact.py, tests/test_store_enroll_cli.py show the shape).

*Observed 2026-10-03 (python-dev)*
