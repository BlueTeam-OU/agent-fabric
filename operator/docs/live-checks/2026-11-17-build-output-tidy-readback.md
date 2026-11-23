# 2026-11-17: the daily build-output tidy, read back on the accounts that filled /home

**Why.** Rust `target/` directories filled /home on develop-qzapp twice:
on 2026-10-20, and on 2026-11-13, when rust-ui-dev-01 held 167G,
rust-ui-dev-02 64G and p2p-network-dev-01 49G. `fabric-jobs tidy` has
run daily on every account since 2026-10-27 (`agent-fabric-tidy.timer`,
1d20e23dd). python-dev-03's cd36f7d1d (j146, on main) added two things
to it: the size of each tree it keeps, and a warning line at 85% used.
This read-back decides whether that is the fence j841 asked for, or
whether something more must be built.

**Measured** (21:00-21:20Z, as fabric-coordinator, through
`fabric-host develop-qzapp run --as <login>`):

- `/home` 639G, 435G used (69%).
- `fabric-ctl all disk`: the three largest `target/` directories are
  rust-ui-dev-01 62.7G (`interweave-j288-…`), rust-ui-dev-02 55.2G
  (`interweave-j121-…`) and rust-services-dev-01 42.3G
  (`InterWeave-j105-…`).
- The timer is installed and lingering on all three accounts. The
  service ran today between 04:47Z and 04:59Z with `Result=success`.
  Each account's `~/projects/agent-fabric` contains cd36f7d1d.
- `fabric-jobs tidy --dry-run` as each account says it would now remove
  all three targets: 62.6G, 55.2G and 42.2G, plus smaller spike targets
  in the same trees.
- j288 was closed at 16:22Z and j121 at 19:39Z, both after today's run.
  Tomorrow's run removes them. That gap is the fence's latency: at most
  a day, by design.
- j105 was closed on 2026-11-16 at 18:37Z, before today's run, but its
  `target/` was modified today at 13:32Z. The tree was in use after its
  job closed. Who was using it, and what this morning's run said about
  it, is not read: the service's lines go to the user journal, and
  `journalctl --user -u agent-fabric-tidy` showed no entries on the
  coordinator's own account, where the same run also succeeded.

**Control.** The same dry run on the coordinator's own account kept
every tree an open job holds, naming the job, and freed 0 B. Tidy tells
held from unheld; the three large targets are unheld only because their
jobs have since closed.

**Not verified.**
- Why `fabric-jobs switch`, which cleans the left job's targets
  (ADR-037 §5 rule 10), left j288's and j121's in place. A session
  still standing in the tree it leaves is one keep reason. That is a
  question for python-dev (j841).
- Whether the 85% line reaches anyone. The journal is not a reader.
  The coordinator's reads are `fabric-ctl all disk` and the machine row
  of `fabric-ctl all status`.

**Decides.** The daily sweep works on the accounts that filled the disk.
What it leaves is up to a day of output from jobs closed after the run,
plus whatever `switch` misses. ADR-010 §5 rule 13 records the division
(A 2026-11-17).
