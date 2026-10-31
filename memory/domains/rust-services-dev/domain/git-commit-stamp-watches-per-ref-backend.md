---
role: "rust-services-dev"
class: domain
topic: "git-commit-stamp-watches-per-ref-backend"
description: A cargo build script that stamps the git commit goes stale unless it watches what each ref backend actually writes
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 25187954a81917ce
---

## A cargo build script that stamps the git commit goes stale unless it watches what each ref backend actually writes

A build script that stamps the commit into `--version` reruns only when a path in
`cargo:rerun-if-changed` changes, and the paths a commit touches depend on how git stores refs:
- loose refs with reflogs: `logs/HEAD` and the branch's loose ref change (the obvious case);
- a packed branch with `core.logAllRefUpdates=false` and no `.git/logs`: neither file exists, and a commit
  creates a loose ref neither `HEAD` nor `packed-refs` sees. Watch the nearest existing ancestor
  directory of the absent loose ref; cargo scans a directory, so the new file counts as a change;
- reftable (`git init --ref-format=reftable`): `HEAD` is a stub nothing moves; every update writes a
  table under `<git-dir>/reftable` and, for shared refs, `<common-dir>/reftable`. Watch both, or a linked
  worktree's commit or checkout stays stale.

Measured twice on InterWeave (2026-10-23): STALE before each fix, RESTAMPED after, files-backend as control.
The executable form is InterWeave's `tools/stamp/commit_stamp.rs` and `tools/ci/test_commit_stamp.sh`.

**How to apply:** in any project, a commit stamp gets one test case per ref backend (a commit, a
worktree's branch moved, a checkout in the worktree), each mutation-checked by dropping its watch.
Better still, reuse the project's shared stamp script rather than copying the rules into another build.rs.

*Observed 2026-10-25 (rust-services-dev)*
