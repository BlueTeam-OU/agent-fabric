---
role: "edge-hosting"
class: workflow
topic: "home-disk-footprint"
description: "What fills the edge-hosting home on develop-qzapp, what is safe to remove in a disk cleanup, and how to record a cleanup that has no repository artifact"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "edge-hosting"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 58c502301dd10ddd
  - 93f83ae113960982
---

## What fills the edge-hosting home on develop-qzapp, what is safe to remove in a disk cleanup, and how to record a cleanup that has no repository artifact

The edge-hosting home on develop-qzapp builds nothing, so it holds no build output to clean. On 2026-10-17 it was 2.9G. Most of it was in four places:
- `~/.local/share/claude/versions/`: about 240M per Claude Code version. Old versions pile up after each upgrade. Keep only the version pinned in `runtime/claude-code/harness.json` (`"claude"`), and first check that no process still runs an old binary (`readlink /proc/<pid>/exe`).
- `~/.local/share/pnpm` (865M): `pnpm store prune` frees nothing here. Its `store/v11` (566M) is only a download cache for checkouts' `node_modules`. Once those are removed it can be deleted outright, and the next install refetches it (done 2026-10-24, when /home was full: home 2.1G to 1.5G). Keep `package-manager-store` (300M): pnpm itself lives there.
- `~/.cache/pip` and `~/.cache/pnpm`, and the npm cache (`npm cache clean --force`): safe to remove.
That cleanup took the home from 2869M to 2030M (job j13, after broadcast 01a14a95-abad-700f-aa4f-f47855c50580).

**Why:** the host's disks filled on 2026-10-17 and the fleet went down twice. The owner asked every agent to clean its own home.

**How to apply:** a cleanup leaves no PR, commit or reply. Close its job with `fabric-jobs done <id> --no-artifact "<what was done>"` (agent-fabric #299, merged 2026-10-18; decided by fabric-coordinator in 01a14f01-1394-70e7-b6c4-bd2728a4f3ad). `switch` accepts that, and the same command settles a job already stuck done without evidence (j13 was).

At every job end, before `fabric-jobs switch`, remove what only that job needed: merged worktrees (then `fabric-branches --sweep`), build output, review heads, scratch in `$TMPDIR`. Measure it first with `du -sh`, touch only my own files, and name what went in the job's evidence (fabric-coordinator's broadcast 01a150ca, 2026-10-18). `$TMPDIR` is `~/agent-fabric-tmp` now, not under /var/tmp.

*Anchors: `runtime/claude-code/harness.json::"claude"`, `tools/fabric/jobsparts/settle.py::no artifact`*

*Observed 2026-10-18 (edge-hosting)*
