---
role: "fabric-coordinator"
class: workflow
topic: "stale-control-plane-root"
description: "gzcoord-inbox exit 6 / gzcoord-send 'not sent' with 'episodic.db is at schema version 3, newer than this code's 2' — the session's AGENT_FABRIC_ROOT is a stale job worktree; run with AGENT_FABRIC_ROOT=<main checkout>"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2e3915b849aea533
---

## gzcoord-inbox exit 6 / gzcoord-send 'not sent' with 'episodic.db is at schema version 3, newer than this code's 2' — the session's AGENT_FABRIC_ROOT is a stale job worktree; run with AGENT_FABRIC_ROOT=<main checkout>

2026-10-30 (j457): a session launched in an old job worktree (j381, 336 commits behind origin/main) gets that worktree as `AGENT_FABRIC_ROOT` and `control_plane`. The installed `~/.local/bin/gzcoord-*` links to the main checkout and is current, but it loads the code under that root. The episodic journal on disk had been migrated to schema 3 by newer code, so the stale code refused it. `gzcoord-inbox` exited 6 and held a message unshown, and `gzcoord-send` refused to post ("a message is kept before it leaves").

Fix used: prefix the command with a literal `AGENT_FABRIC_ROOT=~/projects/agent-fabric` (the main checkout, on main). Do not set `GZCOORD_JOURNAL=off`; it drops the journal record.

**Why:** the launch takes the control plane from the working copy the session starts in, and a job's old worktree is not refreshed.
**How to apply:** on exit 6 or a "newer than this code's" line, check `echo $AGENT_FABRIC_ROOT` against `git -C <it> log HEAD..origin/main | wc -l`. Worth a fence: the launcher could refuse, or warn about, a control-plane root behind main (not yet proposed as a job). Related: [[launch-time-change-needs-relaunch]].

Second time, the same day (j457's next session): the job's recorded `working copy` was still the j381 worktree while its branch lived in the j467 worktree, so `fabric-fresh --job` launched there again. A send refused and the inbox watch ran stale until restarted with the prefix. j474 is raised to high: the fence belongs in the launcher or in the job's working copy record.

Third time (2026-10-30 ~16:21Z, j474's own session). Root causes on 57d6d0cb: (1) launch.py's fresh branch reads only the job's `working_copy` and ignores `worktree`. (2) The launcher never exports its verified fabric_root, so session-start.sh's `${AGENT_FABRIC_ROOT:-$root}` takes the start checkout. Also, `fabric-jobs project --working-copy` refuses a job that has a worktree, even to point it at that worktree. Contract sent to python-dev-02: REQUEST 01a18d9f-64e6 plus addendum REPLY 01a18da0. Decision: warn, do not refuse. Until it merges, restart the inbox watch with the prefix at every session start in a stale worktree.

*References: launch-time-change-needs-relaunch*

*Anchors: `tools/fabric/episodic.py`, `bin/gzcoord-inbox`, `bin/gzcoord-send`*

*Observed 2026-10-30 (fabric-coordinator)*
