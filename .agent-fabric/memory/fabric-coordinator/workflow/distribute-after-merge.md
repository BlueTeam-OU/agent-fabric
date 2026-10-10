---
role: "fabric-coordinator"
class: workflow
topic: "distribute-after-merge"
description: "After a fabric PR merges, distribute it to every account yourself — fabric-ctl all upgrade fabric, run before moving your own checkout — a broadcast alone is not distribution"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - c1a54fb163856f15
  - fff4824d16e5df94
---

## After a fabric PR merges, distribute it to every account yourself — fabric-ctl all upgrade fabric, run before moving your own checkout — a broadcast alone is not distribution

On 2026-09-23 I merged #31 and sent a GZCoord broadcast telling every
agent to relaunch, reasoning that the launcher pulls `main` itself at the
next launch. The owner: "still you haven't distributed the upgrade to all
agents — now it is merged." A broadcast is news; distribution is the
upgrade actually on every account.

**Why:** an agent that doesn't relaunch for a day runs a day on the old
fabric, and some can't relaunch at all (language-culture-ru's checkout sat
on its PR branch; the launcher's ff-only pull refused, so it could not
start). Only the coordinator can see and fix that across the fleet.

**Since #47 (merged 2026-09-26, 0ec9159): `fabric-ctl all upgrade fabric`**
is how distribution is done — fast-forward to the coordinator's origin/main
sha, bootstrap for the running session's provider, no session stopped, one
row per account; first run 9.5 s for 16 accounts ([[fleet-ops-via-control-plane]]).
The hostexec loop below is NOT a fallback to reach for: `git pull --ff-only
origin main` on a checkout sitting on a branch fast-forwards THAT BRANCH to
main and reports rc=0 (language-culture-ge's merged #44 branch, 2026-09-26);
the command refuses such a checkout by name instead. Use the loop only for
an account whose daemon predates a change to `upgrade` itself, and check
each checkout is on main first.

**How to apply (stopgap):** after a merge, for every account in `fabric-ctl all`,
through `runtime/hostexec/hostexec develop-qzapp --as <login> -- …`:
`git pull --ff-only origin main`, then `runtime/claude-code/bootstrap.sh`
— in that order; a bare pull under a live session gets its reviews
refused (routing moves, the agent files don't). Before bootstrap, check
each account's provider from its installed `code-review.md` model line:
bootstrap under `sudo env -i` installs for anthropic by default, and a
broker session would get the wrong reviewer pin. A checkout that cannot
fast-forward is never forced: find out whose work it is, confirm it is on
the remote, and only then move the checkout to `main`, leaving the branch.
Verify with `fabric-ctl all fabric`; a silent row right after bootstrap is
usually its control agent restarting — ask it alone before re-bootstrapping
([[control-plane-daemon]]). Then announce, naming what each agent must do.

Host-wide installs are not per account and are not refreshed by pull +
bootstrap: /usr/local/bin/moveto stayed at 2026-09-16 while #38 added its
role column, and the owner found it (2026-09-26). After a merge that
touches runtime/provisioning/moveto/, also run
`bin/fabric-host <host> run -- sudo -n bash @fabric/runtime/provisioning/moveto/install.sh`
and check `bin/fabric-status` says `moveto in sync`.

Run it from a checkout ON main, and do not pull that checkout just
before: the command fetches origin/main itself, and a pull that changes
runtime/control/ restarts this account's own daemon, which then misses
the request ("no answer" for user, 2026-09-26 after #49; asked alone a
minute later it read current). The first real upgrade: 15 upgraded
0ec9159 → f40c16a, sessions untouched, each daemon restarting after its
reply.

**Order when my own checkout is on the merged PR branch** (#52 and #53, 2026-09-27: my row read "no answer" both times). Switching my checkout to main changes the control agent's source, and it exits for systemd to restart ("source changed", about 7 s). An `all upgrade fabric` sent in that window gets no answer from my account. Either switch my checkout first and wait for `fabric-ctl user status` to answer before `all upgrade fabric`, or run the upgrade while still on the branch (my row is refused as "not main") and fast-forward mine after. My daemon also restarts on every branch switch in this checkout: it runs whatever branch I have checked out.

**A ping is not proof the restart is over** (#54, 2026-09-27): after switching my checkout, the OLD control agent answered a ping before it noticed the source change, then exited; the upgrade sent next got no answer and `fabric-ctl` waited out its whole budget. Order that worked: `all upgrade fabric` first while still on the branch (mine is refused, the other fifteen move), then switch my checkout, wait until journalctl shows "Started agent-fabric-agentd" after the switch (about 7 s), then `fabric-ctl user upgrade fabric` (it answers `current` and bootstraps).

*References: control-plane-daemon, fleet-ops-via-control-plane*

*Observed 2026-09-23 (fabric-coordinator)*
