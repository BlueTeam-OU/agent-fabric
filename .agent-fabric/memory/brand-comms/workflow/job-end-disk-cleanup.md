---
role: "brand-comms"
class: workflow
topic: "job-end-disk-cleanup"
description: "When a job ends, before fabric-jobs switch: measure and remove what only that job needed in your own account, and write what went into the job's evidence; where brand-comms' disk actually goes"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - cae90ee161b4a801
---

## When a job ends, before fabric-jobs switch: measure and remove what only that job needed in your own account, and write what went into the job's evidence; where brand-comms' disk actually goes

The owner has asked four times in a week for every account to clear its
disk: the 2026-10-17 /var/tmp outage and the full /home of 2026-10-24.
/home is one volume shared by every account, so one account's leftovers
fail every other account's builds and commits.

**How to apply,** when a job is done, delivered or dropped, before
`fabric-jobs switch`:
- `du -sh` first; remove only your own files, and only what nothing
  running uses.
- `fabric-branches --sweep` (`--all` for every clone). It removes
  branches already on main, clean pushed worktrees and the scratch of
  ended sessions. It also removes a clean worktree that a live job
  still names; `git worktree add <path> <branch>` restores it.
- For brand-comms the bulk is `node_modules/` and `dist/` in the site
  and deck clones, `~/.npm` and the pnpm store. Each `npm ci` brings
  them back.
- The harness keeps every Claude Code version it updated to under
  `~/.local/share/claude/versions/` (about 230 MB each). Remove all but
  the one `~/.local/bin/claude` points to.
- Browser and package caches (`~/.cache/{google-chrome,mozilla,libdnf5,pip}`)
  are safe to remove. Keep the profiles under `~/.config`.
- A directory in /var/tmp or elsewhere owned by another login stays,
  however stale it looks.
- Keep a port's oracle or reference renders while its PR is open, and
  remove them at the merge.
- Write what went, and how much, into the job's evidence, e.g.
  `fabric-jobs done <id> --no-artifact "<what, sizes>"` for a clean-up
  of its own.

Related: [[node-to-python-port-parity-traps]].

*References: node-to-python-port-parity-traps*

*Anchors: `tools/fabric/branches.py::session scratch`*

*Observed 2026-10-24 (brand-comms)*
