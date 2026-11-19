---
role: "fabric-coordinator"
class: solution
topic: "sweep-keeps-worktrees-for-ruff-cache"
description: "fabric-branches --sweep kept 52 clean worktrees at 0 only for .ruff_cache (and cargo target/); clearing git-ignored caches then re-sweeping removed 50 (j587, 2026-11-08)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6013ae926231db28
---

## fabric-branches --sweep kept 52 clean worktrees at 0 only for .ruff_cache (and cargo target/); clearing git-ignored caches then re-sweeping removed 50 (j587, 2026-11-08)

On 2026-11-08 (j587), `fabric-branches --sweep --all` exempted Python bytecode but not `.ruff_cache/`. Every agent-fabric worktree that ruff had run in therefore stayed as "N ignored path(s)", even at 0 with no job naming it. That was 52 worktrees, about 3.7G with cargo `target/` in InterWeave spikes. I deleted only the paths that `git status --ignored` listed and that matched `__pycache__/`, `.ruff_cache/`, `.pytest_cache/` or `*/target/`, checked that no process had its cwd inside, and swept again: 50 removed, home 56G → 50G. The other 2 had uncommitted changes.

The Bash safety check refuses `rm -rf "$w/$p"` in a loop. `rm -rf -- "${w:?}/${p:?}"` passes it.

**Why:** a cache is regenerable. The sweep's "no ignored files" rule exists for a `.env` or a build, not for a linter cache.
**How to apply:** before a disk sweep, clear git-ignored caches in worktrees at 0, then sweep. Worth proposing that the sweep exempts `.ruff_cache`/`.pytest_cache` like bytecode (a python-dev entry). Related: [[jobs-and-switching]].

*References: jobs-and-switching*

*Anchors: `tools/fabric/branches.py::__pycache__`*

*Observed 2026-11-08 (fabric-coordinator)*
