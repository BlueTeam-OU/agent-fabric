# ADR-034 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-30 — Doppler is retired: the stores replace it

Doppler is removed (ADR-038, agent-fabric #69): the §1 inventory's signed-actions and secrets rows name the stores that replaced it, and rule 4 no longer lists Doppler among the services an identity must not depend on.

### Amendment 2026-10-27 — The relay's database is copied off the host: step 1 of §7 done

The relay's database is now scheduled to be copied every 6 h to Proton Drive, encrypted and signed (`fabric-secrets relay backup`, agent-fabric #404; `agent-fabric-relay-backup.timer`, installed by bootstrap on the relay's account only), and a restore was read back: a second relay served the copy and `gzcoord-inbox --replay` returned the channel's past (`docs/live-checks/2026-10-27-relay-backup-restore.md`). The §1 relay row's "if it fails" no longer says the past is lost, §6 no longer says nothing backs it up, and §7's first step is recorded as done. The timer's scheduled runs and a restore off the host are not shown. The live check does not include `fabric-ctl all ping` on the restored relay; that stays with the relay-down drill.

### Amendment 2026-10-28 — Undrained memory has a daily copy; §7 step 3, the scheduled drain, decided

The §1 row for an agent's undrained memory said it was lost with the host. Since j179 the login's daily state backup (`agent-fabric-state-backup.timer`, `tools/fabric/secretstore/statecopy.py`) copies `~/.claude/projects/*/memory/**` into the login's own store, which its parent's backup carries to Proton Drive; on 2026-10-28 the coordinator's run of 00:28 CET ended in success. No restore of that copy has been read back, so the row's degraded mode stays "none documented" (§5 rule 3). §3 and §6 say the same, and §2 no longer offers it as memory on one host only. §7 step 3 is decided as a design, not yet built: the bound is 14 days outside the corpus; a weekly timer on the coordinator's account collects every account's bundle with `fabric-ctl all memory`, an unsigned read; each run writes a report, unknown for an account that did not answer, and keeps one drain job on the coordinator's list; `fabric-status` prints the oldest undrained memory's age. Assembly and landing stay reviewed by hand, and so does issuing the reflection passes. The drain had last run on 2026-10-18 (`.agent-fabric/memory/last-drain-report.json`).

### Amendment 2026-11-07 — The relay down for a working hour: step 2 of §7 done

The relay was stopped on purpose from 22:19:40Z to 23:20:19Z on 2026-11-07 and started again on a copy restored from its backup (`docs/live-checks/2026-11-07-relay-down-drill-hour.md`, j622). The first attempt, on 2026-11-05, ended after 18 minutes when a re-armed watch restarted the relay; its four defects were fixed before the re-run (#499, #501, #504, #505). Sessions went on from artifacts, 9 commits against 10 in the hour before; the restored copy matched the stopped original, seq continued without a gap, every account's control agent answered `fabric-ctl all ping` through it (the item the 2026-10-27 amendment left to the drill), and the five messages minted in the window were on the relay within about three minutes of the restart. §7 records the step as done and the timer's scheduled runs as read back; the human relay was not needed and stays unexercised, so §6's line on degraded modes is unchanged. A restore off the host is still not shown.
