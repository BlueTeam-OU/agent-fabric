# 2026-11-23: tidy's held-tree sizes, read back after e2635f1f reached the accounts

**Why.** The 2026-11-17 read-back
(`2026-11-17-build-output-tidy-readback.md`) found the daily tidy
removing unheld targets; its control showed held trees kept and named
by job, on an account with nothing large held. Since then e2635f1f
(#617, python-dev-03) made a held tree that cannot be listed say it
could not be measured, instead of printing a smaller size or 0 B. This
read-back (j901) checks the held-tree line on an account that holds
real build output, after that change was distributed.

**Measured** (16:00-16:20Z, as fabric-coordinator, through
`fabric-host develop-qzapp run --as <login>`; both holders were asked
first, at 07:23Z and 07:28Z, and neither request was queued):

- Both rust accounts' `~/projects/agent-fabric` are at e4384768, which
  contains e2635f1f (`fabric-ctl <login> fabric`).
- `fabric-jobs tidy --dry-run` as rust-ui-dev-01:
  - kept `interweave-j311-…`, held by open job j331, "its build output
    is 50.8 GB";
  - kept `interweave-j330-…`, held by open job j330 (active), "its
    build output is 44.5 GB";
  - kept j232's, j310's and j316's checkouts with no size line, as they
    have no build output;
  - would remove `interweave-j327-…/target` (9.6 GB); would free 9.6 GB.
- The same as rust-services-dev-01: nothing to keep or remove, would
  free 0 B. That account's `target/` total is 0K (`fabric-ctl
  rust-services-dev-01 disk`).
- `/home` on develop-qzapp: 639G, 405G used, 235G available (64%). The
  85% warning line is not printed, as expected.

**Control.** The held sizes against `du`, run as the same account:
j311's top `target` is 54,523,621,376 bytes on disk, 50.8 GiB. j330's
top `target` is 41.6 GiB, which is what `fabric-ctl disk` lists; with
the spike targets nested in the same checkout the total is
47,759,249,408 bytes, 44.5 GiB, which is tidy's figure. Tidy sums every
`target` in a held tree, and `disk` lists the top one, so the two
figures differ for j330 and both are right.

**Found.** Tidy's sizes are binary (powers of 1024) under the label
"GB" (`human()` in `tools/fabric/jobsparts/leave_targets.py`, which
tidy uses, steps by 1024). `fabric-ctl disk` prints the same
quantities as "G". The numbers agree; the label understates by 7%.
Cosmetic, not filed.

**Not verified.** No held tree on these accounts was unlistable, so the
"could not be measured" line of e2635f1f was not seen live; its tests
on main cover it.

**Decides.** j146's held-size line works on a live account with 95 GiB
held: each held tree names its job and its whole build output, and the
dry run's "would free" counts only what no open job holds. The
remaining disk pressure on rust-ui-dev-01 is held by its own open jobs
j330 and j331, which is that account's to settle, not tidy's.
