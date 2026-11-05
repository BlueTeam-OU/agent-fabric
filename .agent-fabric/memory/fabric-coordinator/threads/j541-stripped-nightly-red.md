---
role: "fabric-coordinator"
class: threads
topic: "j541-stripped-nightly-red"
description: "j541 handover: stripped-nightly red 12 days unnoticed (last green 2026-10-19); five files, each red from its own day, so five separate regressions, not one runner change"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - dc6152f5cde0dd0c
---

## j541 handover: stripped-nightly red 12 days unnoticed (last green 2026-10-19); five files, each red from its own day, so five separate regressions, not one runner change

2026-11-01, read-only diagnosis in j540's session (owner asked "do j541" mid-j540; j541 needs its own session).

Last green stripped-nightly: run 39194081816, 2026-10-19. Every run since is red, and no job or message noticed it for 12 days. That is the first thing to fix: a red scheduled run must reach a job (alert path), not only the Actions tab.

Each failing file went red on its own date, so these are regressions that landed on main and passed `ci` (which runs on the full tree), not the Ubuntu-26 runner migration:
- harvest_memory from 10-21: anchor cases (`tools/c.py::main`) read the registry the stripped tree lacks
- control_ctl from 10-23: `pool-add` reads the role catalogue at parse time, so `--help` exits 2
- self_kill_guard from 10-23: stand-in processes not exec'd under their names "before any case asks"
- review_mcp from 10-24: the bwrap control (tmpfs on a symlink destination) fails in the copy
- cpu_lease from 10-31: `policies/host-load.json` is stripped as instance data
- transient: branches_sweep (10-20), addenda (10-21, 10-25), store_enroll_cli (10-25, 10-27)

Per-run list: scratchpad nightly_hist.sh (gh run view --log, grep `^tests/…: FAILED`). Mechanism: tests/stripped_run.py + tests/stripped_skip.txt (a red file is listed with its owning job, and leaves the list in its fixing commit).

**How to apply:** in j541's session, `git log --since` on each file's introduction date to find the commit and its holder, contract each fix (or skip-list entry with a job) to that holder, and add the alert. Related: [[checks-need-a-control]].

2026-11-02 state: suite fixes contracted to python-dev-02 (their j108, REQUEST 01a19af7-d2f7, acked 01a19af8-902d). Alert contracted to python-dev-02 too (REQUEST 01a19b0f-cd21): `tools/fabric/github/scheduled_red.py --repository --workflow [--branch] [--project] [--dry-run]`, adds a high ci job with marker `[scheduled-red:<repo>/<wf>]`, exit 3 on unread. Mine on their branch when they REPLY: runtime/control/agent-fabric-scheduled-red.{service,timer} (after 03:17 cron + 90 min cap, e.g. 06:00 UTC, coordinator account only, as relay-backup) + bootstrap.py step. j541 blocked on job:python-dev-02/j108 + j109 (alert, REPLY 01a19b10-b848).

2026-11-03 state: #461 (five suites) and #462 (alert + timer + bootstrap) merged. The 11-03 nightly (41622247557) was red on one new case: test_scheduled_red "a registered repository files under its id" reads the live projects/registry.json. Contracted to python-dev-02 (REQUEST 01a1a147-a3aa). It asks them to cherry-pick my 5784af63 too: the timer moves 07:00→17:00 UTC, because the scheduled runs start 08:56–10:58 UTC and 07:00 read the day before's run. They took it as their j110 (REPLY 01a1a148); j541 is now blocked on job:python-dev-02/j110. **How to apply:** After it merges, check that the next scheduled nightly is green apart from the listed reds and that the 17:00 timer filed no job, or exactly one if the run was red; then close j541 together with j561 (distribution).

2026-11-04 00:05Z state: #466 merged (a69d0271, on main); its branch was green in dispatch run 41634899194. The 11-03 17:05 UTC timer filed exactly one job, j578, for the red 11-03 run. I closed j578 as a duplicate fixed by #466. The alert path is now proven live. The "red since … (no success in the last 15 completed runs)" line counts scheduled runs only, so a green dispatch does not reset it. j541 is blocked on clock:2026-11-04T17:20Z. **How to apply:** at 17:20 UTC, check that the 11-04 scheduled run is green and that the 17:10 UTC timer filed no job. Then close j541 and j561.

*References: checks-need-a-control*

*Observed 2026-11-01 (fabric-coordinator)*
