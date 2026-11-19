---
role: "fabric-coordinator"
class: workflow
topic: "relay-drill-procedure"
description: how to take the GZCoord relay down on purpose and bring it back on a restored copy, and what is dark meanwhile
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 83a1eae6da53db29
  - f2e7baa72d40f504
---

## how to take the GZCoord relay down on purpose and bring it back on a restored copy, and what is dark meanwhile

The relay-down drill (j622, `docs/live-checks/2026-11-07-relay-down-drill-hour.md`) worked in this order: baseline (commits via `git log --remotes=origin` by committer date per clone — the GitHub events API lags and has no sizes; channel counts from the DB read-only), broadcast INFO, `systemctl --user stop gzcoord-relay.service` (clean in 5 s since #501), `fabric-secrets relay backup` + `--verify` of the stopped DB, `fabric-secrets relay restore <empty dir>`, compare seq/cursors/events, at the end move db+wal+shm aside together and the restored db into `~/projects/.gzcoord/`, start, broadcast "back".

- `fabric-ctl` (presence, ping, `fabric-jobs` state stream) rides the relay: dark for the whole outage. Ping answers ~20 s after start, not 6 s.
- An outbound journal row is in `~/.local/state/agent-fabric/agents/<login>/episodic.db`, table `episodes`, columns `source='gzcoord'`, `happened_at`, `carrier`.
- Opening the restored db with `sqlite3 ?mode=ro` leaves `-shm`/`-wal` beside it: remove them with the dir.
- Until #506's hook half merges, the Stop hook demands a re-arm every 15 min while the relay is down; harmless since #504 (an operator stop holds).

- Keep the moved-aside original a day, then delete it once `systemctl --user show gzcoord-relay.service -p ActiveEnterTimestamp -p NRestarts` shows a day up with 0 restarts and `fuser` finds no user (j637, 2026-11-09: 1,069,711,360 bytes freed).
- The relay logs to the journal since 2026-11-12 (`journalctl --user -u gzcoord-relay`; j789 installed and restarted it, read back: StandardOutput=journal, bridge.log static). Before that the unit appended to `bridge.log`, which nothing rotated (1.8 GB left beside the db, j686). Only the detached-spawn fallback still writes bridge.log.

Related: [[gzcoord-messaging]], [[dated-threads-and-jobs]].

*References: dated-threads-and-jobs, gzcoord-messaging*

*Anchors: `communication/gzcoord/runtime/gzcoord-relay.service::ExecStop`, `tools/fabric/gzcoord/inbox_parts/relay.py::_stopped_by_operator`*

*Observed 2026-11-09 (fabric-coordinator)*
