# In-flight view and trial merge, read back on gzapp (2026-09-26)

What was measured, on the gzapp working copy of develop-qzapp/user, with
agent-fabric at the #47 branch and gzapp's origin/main at 982ed83e.

## `pr-gate.sh --in-flight`

26 branches in flight on gzapp, not merged into origin/main; most of them
had no PR — the jobs no earlier tool listed (the verdict rows read open
PRs only).

## `pr-gate.sh --overlap develop-qzapp/backend-dev-02/feat/served-chainage`

The branch architect-cto-01 assigned around the same morning, unseen: six
branches share paths with it, among them architect-cto-01's two supply
branches for it (`for/backend-dev-02/kerb-side-rule`, 28 shared paths;
`for/backend-dev-02/served-chainage`, 19) and #950 through the ADR index.
The view would have shown the job in flight before the assignment.

## `trial-merge.sh <served-chainage> <its served-chainage supply> --check`

- `combines — tree 13e908c404e5`: the two merge cleanly onto 982ed83e.
- `check unavailable (exit 2)`: gzapp's declared check is `make
  trial-check`, whose target lands with gzapp #943; on main it is missing,
  and the result reads unavailable, never a pass — the case devex-tooling
  asked to be pinned (relay seq 6076).
- Exit 2; the gzapp clone's HEAD, status and worktree list identical before
  and after; nothing left under the scratch directory.

## What it decides

Nothing: both tools report. The first run with the check available is due
after gzapp #943 merges — devex-tooling's positive control (ac974f04 +
5404df56 with check_synthetic_client_is_dev_only, expected FAIL) belongs
there, once those are on branches.
