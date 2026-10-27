# ADR-034 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-30 — Doppler is retired: the stores replace it

Doppler is removed (ADR-038, agent-fabric #69): the §1 inventory's signed-actions and secrets rows name the stores that replaced it, and rule 4 no longer lists Doppler among the services an identity must not depend on.

### Amendment 2026-10-27 — The relay's database is copied off the host: step 1 of §7 done

The relay's database is now copied every 6 h to Proton Drive, encrypted and signed (`fabric-secrets relay backup`, agent-fabric #404; `agent-fabric-relay-backup.timer`, installed by bootstrap on the relay's account only), and a restore was read back: a second relay served the copy and `gzcoord-inbox --replay` returned the channel's past (`docs/live-checks/2026-10-27-relay-backup-restore.md`). The §1 relay row's "if it fails" no longer says the past is lost, §6 no longer says nothing backs it up, and §7's first step is recorded as done. The live check does not include `fabric-ctl all ping` on the restored relay; that stays with the relay-down drill.
