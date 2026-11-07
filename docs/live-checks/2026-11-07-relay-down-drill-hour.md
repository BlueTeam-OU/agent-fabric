# 2026-11-07 — the relay down for a working hour

Run by fabric-coordinator, on develop-qzapp, against the live relay (`gzcoord-relay.service` on the coordinator's account, `~/projects/.gzcoord/claude-bridge.db`), with the InterWeave carrier in its dual run (agent-fabric ADR-064). The question is agent-fabric ADR-034 §7 step 2: with the relay down for a working hour, do sessions continue from artifacts, does what must go go by the human relay, and is nothing lost. The drill of 2026-11-05 (`2026-11-05-relay-down-drill.md`) ended after 18 minutes, when a re-armed watch started the relay again; this is its re-run, after the fixes for defects 1, 3 and the relay-restart half of 4 merged (#501, #499, #504); defect 2's fix (#505) merged a minute after the drill ended, and the Stop hook's half of defect 4 is on #506. It ends on the restored copy of the database, as the owner agreed on 2026-11-05.

The relay was down from **22:19:40Z to 23:20:19Z**, 60 min 39 s, and came back on the restored copy.

## What was measured

| when (UTC) | step | result |
|---|---|---|
| 21:19–22:19 | the hour before | 10 commits on origin across the managed repositories (InterWeave 4, agent-fabric 4, agent-fabric-gateway 2; `git log --remotes=origin` by committer date in one clone per remote); 10 messages on `gzapp:gzcoord`, 1 483 on the control channels |
| 22:17:52 | broadcast INFO `01a1b816` with the window and its rules | seq 895 163, delivered back to the coordinator's own watch: delivery worked before the stop |
| 22:19:35 → 22:19:40 | `systemctl --user stop gzcoord-relay.service` | 5 s, unit `inactive`, `Result=success`, no abort and no core dump (2026-11-05 defect 1, fixed by #501's ExecStop). Last message seq 895 322 |
| 22:19:5x–22:25 | `fabric-secrets relay backup` of the stopped database (started right after the stop; the revision is stamped 22:22:53), then `--verify` | 1 059 479 552 bytes uploaded as 231 070 051, 3m52s; the revision decrypts, matches its manifest and passes integrity_check |
| 22:20:26 | `gzcoord-send --force` of an INFO to python-dev-03 | exit 3, "relay unreachable … not sent"; the journal row is `accepted`, carrier `interweave` (defect 2, still on the deployed build: #505, which fixes the line, merged at 23:21) |
| 22:25:3x–22:27 | `fabric-secrets relay restore` into an empty directory | 1m36s, integrity ok; seq 1..895 322, 895 317 messages, 38 consumer cursors, 184 304 events, each equal to the stopped original's, and the cursors' dump hashes identically |
| 22:34:57 | the coordinator's watch, 15 min down | exit 5, the relay-down marker written beside its lock (#504) |
| 22:35:34 | a watch armed on the hosting account, relay stopped | the unit stayed `inactive`/`success`, the port unanswered; at 22:51 the watch printed "gzcoord-relay was stopped on purpose and is left stopped" (defect 4, second half, fixed by #504) |
| 22:19–23:15, every 5 min | `gzcoord-inbox --until-delivery` processes on the host | 58, 58, 60, then **12** at 22:34:57 as the watches gave up, then 44, 44, 42, 42, 42, 44, 44, 44: the fleet re-armed within five minutes and every 15 min after |
| 22:19–23:20 | `fabric-ctl all presence` | "the relay is unreachable" each time: the control plane rides the relay (ADR-029) and was dark for the hour |
| 23:20:19 | the original database (with its `-wal` and `-shm`) moved aside, the restored copy put in its place, `systemctl --user start` | port answered at 23:20:22 |
| 23:20:21 | seq | 895 323, straight after 895 322: no gap |
| 23:20:27 / 23:20:44 | `fabric-ctl all ping` | 8 s after the start (23:20:19): no account answered. 25 s after: **30 of 30 ok**, through the relay on the restored copy |
| 23:20:41–23:23:24 | messages minted in the window (MESSAGE-ID time 22:20–22:28) reaching the relay | five: REPLY from architect-cto-01, OBSERVATION from ux-designer-01, REPLY from rust-ui-dev-01, REPLY from p2p-network-dev-02, and the coordinator's own probe, resent from its file (seq 895 420 – 895 688) |
| 22:19:40–23:20:19 | the work | 9 commits on origin (InterWeave 3, agent-fabric-gateway 4, agent-fabric 2), against 10 in the hour before |

## What it decides

- **Sessions continue from artifacts for an hour without the relay.** 9 commits against 10 in the hour before, in three repositories. The fleet's own coordination was dark for the hour (no message, no control action), and nothing in the record shows a session blocked by it.
- **Nothing in the relay's record was lost.** A copy of the stopped database restores whole; the relay serves it, its seq continues without a gap, and every control agent answers through it. The 2026-10-27 open item, `fabric-ctl all ping` against a restored relay, is closed.
- **What sessions wrote during the hour reached the relay once it was back.** Five messages minted in the window were on the relay within 3 min 5 s of the restart, each with its original MESSAGE-ID (the probe also went by the carrier at 22:20, so its addressee holds one message, not two).
- **An operator's stop holds.** Clean stop, no restart by any watch on the hosting account, and the relay came back only when started by hand.
- **The human relay was not needed** in this hour: no message was handed to the owner. It stays unexercised, and step 2 does not depend on it: an hour without a message cost no session its work.

## What is still open

1. **The Stop hook still re-arms a watch on an unreachable relay**, so every session spins a 15-minute watch while the relay is down (the 12 → 44 above). The hook's half of the relay-down marker is on BlueTeam-OU/agent-fabric#506, unmerged; the relay itself is no longer restarted by it.
2. **The deployed `gzcoord-send` still says "not sent"** when the carrier accepted a direct message; #505 fixes it on main, to be distributed with the next `fabric-ctl all upgrade fabric`. Its wording for a resend from a file (one message, not a duplicate) was decided to python-dev-03 as a follow-up (REPLY `01a1b852`).
3. **The original database** is kept beside the relay's directory (`~/projects/.gzcoord-original-2026-11-07/`, 1.07 GB) until the restored copy has run a day.

## Not verified

- That no message was lost outside the relay's record: a session that got exit 3 and never resent leaves nothing on the relay or in this host's view; the five above are what the relay shows, not every account's journal.
- Whether python-dev-03's watch showed the carried probe during the outage (#499's promise); its reply at 23:21 did not say.
- Any comparison of the fleet's load across the two hours: the commit counts are similar, but neither hour's session count could be read during the outage, since presence rides the relay.
