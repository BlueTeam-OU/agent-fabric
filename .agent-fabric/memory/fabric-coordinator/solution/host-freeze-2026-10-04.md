---
role: "fabric-coordinator"
class: solution
topic: "host-freeze-2026-10-04"
description: "develop-qzapp froze 2026-10-04 (journald silent 16:33-19:43, owner killed it); memory exhaustion into zram thrash with no killer; owner applied systemd-oomd + per-login 10G/12G caps"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e2cc8b436b047df6
---

## develop-qzapp froze 2026-10-04 (journald silent 16:33-19:43, owner killed it); memory exhaustion into zram thrash with no killer; owner applied systemd-oomd + per-login 10G/12G caps

On 2026-10-04 develop-qzapp's qube froze; the owner killed it at 19:46.

**What the evidence showed.**
- The system journal had nothing from 16:33 to 19:43: journald fell silent while agents kept working, since relay messages were still sent in that window.
- No OOM kill or hung-task line was logged.
- There was no killer: systemd-oomd was inactive, user slices were uncapped, and the qube has 8 GB of zram swap at swappiness 60.
- In that window, rust-ui-dev-01's InterWeave target regrew to 48 GB, so a heavy rustc load was running beside 18 sessions.
- Disk was not full (/home 57%, / 44%).

**Diagnosis:** memory exhaustion that slid into zram thrash, not a crash. It cannot be fully proven, because it was not logged.

**Applied by the owner, as root, persistent in this standalone qube:**
- `systemctl enable --now systemd-oomd`;
- `/etc/systemd/system/user-.slice.d/50-agent-fabric-memory.conf`: MemoryHigh=10G, MemoryMax=12G, ManagedOOMMemoryPressure=kill, limit 50%;
- `/etc/systemd/system/-.slice.d/50-agent-fabric-swap.conf`: ManagedOOMSwap=kill.

Verified: all 18 user slices are capped, and oomctl lists every user slice and `/`.

**Diagnosing a later freeze** without root: `journalctl -b -1` shows only your own user journal. Ask the owner for `sudo journalctl -b -1 -o short-monotonic`. A wall-clock gap whose monotonic time also jumps means the qube ran and did not log.

**Open fabric follow-ups:**
- agentd samples /proc/pressure/memory and free memory every minute into its own state, so a post-mortem has data even when journald stalls;
- heavy builds run under `fabric-lease heavy-build -- …` with capped jobs (devex-tooling, InterWeave roles).

*Observed 2026-10-04 (fabric-coordinator)*
