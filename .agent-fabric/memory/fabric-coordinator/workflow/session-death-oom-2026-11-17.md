---
role: "fabric-coordinator"
class: workflow
topic: "session-death-oom-2026-11-17"
description: "A session that dies with no transcript record and no relaunch: read memory-pressure.json and /proc/vmstat oom_kill before suspecting fabric-fresh or the account switch (2026-11-17, 31 h coordinator session)"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c435225d02ac525d
---

## A session that dies with no transcript record and no relaunch: read memory-pressure.json and /proc/vmstat oom_kill before suspecting fabric-fresh or the account switch (2026-11-17, 31 h coordinator session)

2026-11-17: my j830 session `7053b9f8` died without a relaunch, and the owner restarted it by
hand. It had been running for 31 h in the j794 copy, with 1441 messages and an 18 MB transcript.

**What happened.** Its last turn ended cleanly at 07:42:15Z, with the stop hooks green and only
the inbox watch running. After that the transcript has nothing. `memory-pressure.json` (one row a
minute in my state dir) shows:
- available memory falling from 12.6 GB at 07:42 to 6.2 GB at 07:43, with full_avg10 at 9.35;
- then back to 15.4 GB at 07:44, so about 9 GB was freed at once.

`/proc/vmstat` `oom_kill 1` was the only kernel OOM kill since the 11-15 boot. Swap was about
6 of 9 GB in use. systemd-oomd is not installed, so this was the kernel OOM killer.
`dmesg_restrict=1`, so the victim's name needs root (`sudo dmesg -T | grep -i kill`).

**Ruled out:**
- fabric-fresh: exit 137 there is the planned end of the old harness.
- The account-switch controller: in advise mode, with "no move logged yet".
- fleetdeck and ptyxis: both up since 11-15.

**How to apply:** for a session that died silently, read the pressure file and `oom_kill` first.
A very long session is the OOM killer's likeliest pick, so switch jobs into fresh sessions rather
than letting one session live for days. Related: [[claude-ancestor-is-daemon-2-1-322]].

*References: claude-ancestor-is-daemon-2-1-322*

*Observed 2026-11-17 (fabric-coordinator)*
