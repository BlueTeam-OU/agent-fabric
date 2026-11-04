---
role: "python-dev"
class: solution
topic: "fabric-jobs-tidy-j90"
description: "j90 #410 — fabric-jobs tidy (daily build-output tidy); review traps in scan/judge, mutation-script and process lessons"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - af31e916410d89b4
---

## j90 #410 — fabric-jobs tidy (daily build-output tidy); review traps in scan/judge, mutation-script and process lessons

`tools/fabric/jobsparts/tidy.py` (#410, merged 2026-10-27): `fabric-jobs tidy [--dry-run]` walks `~/projects/*` with a `.git`, skips trees overlapping an active/queued/paused/blocked job's worktree/working_copy (delivered is NOT open), and runs `leave_targets.judge()` (shared with `switch`) on `target` beside Cargo.toml and `node_modules` beside package.json. Judge adds: `tracked()` via `git ls-files`, and `scan()` refuses any file, directory, link or the target itself owned by another uid (unlink needs only parent write, so root-owned files in an own-uid dir were deletable). Unknown job state / non-dict entry / unreadable list or ~/projects = exit 1, nothing removed; missing ~/projects = exit 0.

**Why:** review found: owner checked at tree root only; test scratch under TMPDIR=~/agent-fabric-tmp reads the real ~/.cargo via the parent walk (use dir="/tmp", no silent fallback); unknown state counted as closed; os.walk shows only children (target's own uid), and the islink skip ran before the uid test.

**How to apply:** a mutation script that restores after the run must trap EXIT and never be piped into `head` (SIGPIPE left two mutations planted). Foreign-uid tests patch `os.lstat` per basename (SimpleNamespace copy of st_*), not `os.getuid`, so file and dir checks are each pinned. New tests/test_*.py are globbed by the runner (no registration); a new jobsparts file goes into ORDER in tests/test_jobs_parts.py. `fabric-review brief` rejects an objective that "names what was fixed". Launch CLI group 6 stays red locally (see [[fresh-launch-dirty-copy-j89]]).

*References: fresh-launch-dirty-copy-j89*

*Observed 2026-10-27 (python-dev)*
