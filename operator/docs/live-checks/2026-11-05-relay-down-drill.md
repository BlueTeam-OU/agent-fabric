# 2026-11-05 — the relay down: a drill planned for an hour, ended after 18 minutes

Run by fabric-coordinator, on develop-qzapp, against the live relay (`gzcoord-relay.service` on the coordinator's account, `~/projects/.gzcoord/claude-bridge.db`), with the InterWeave carrier in its dual run (agent-fabric ADR-064). The question (agent-fabric ADR-034 §7, step 2): with the relay down for a working hour, do sessions continue from artifacts, does what must go go by the human relay, and is nothing lost.

The answer is partial. The relay was down from 15:50:19Z to 16:08:24Z, not an hour: the coordinator's own inbox watch started it again (below). What follows is what those 18 minutes measured.

## What was measured

| when (UTC) | step | result |
|---|---|---|
| 15:38 | baseline, the hour before | 18 commits on origin across the managed repositories (InterWeave 14, agent-fabric 4); 5 messages on `gzapp:gzcoord`, 1 483 on the control channels; relay at seq 855 999. The fleet's Claude account stood at 98 % of its 7-day window, so the fleet was already throttled |
| 15:40:35 | broadcast INFO `01a1ac5e` with the window and the rules for it | seq 856 150; delivered back to the coordinator's own watch, the control that delivery worked before the stop |
| 15:50:19 | `systemctl --user stop gzcoord-relay.service` | the relay ignored SIGINT for the unit's 10 s stop timeout and was killed by SIGABRT (Fedora's `10-timeout-abort.conf`), core dumped, unit `failed (Result: timeout)`. Last message seq 856 538, at 15:50:12 |
| 15:51:56 | `fabric-secrets relay backup` on the stopped database, then `--verify` | 1 023 430 656 bytes uploaded as 223 713 048, 1m39s; the revision decrypts, matches its manifest and passes integrity_check, the abort notwithstanding |
| 15:51:00 | `gzcoord-send` of an INFO to the coordinator itself | without `--force`: exit 4, "presence is unknown … not sent". With `--force`: exit 3, "relay unreachable … not sent"; journal row `failed`; the carrier did not carry it (no recipient but the sender) |
| 15:51:47 | `gzcoord-send --force` of an INFO to devex-tooling | exit 3 and "not sent" again, **but** the journal row is `accepted` and the carrier's `receipts_in` rose 266 → 267: InterWeave carried it and the addressee's carrier receipted it |
| 15:53 | the fleet's watches | 28 `gzcoord-inbox --until-delivery` running; devex-tooling's, armed 15:42:14, did not end on the carried probe |
| 15:50–16:05 | `fabric-ctl all presence`, every 5 min | "the relay is unreachable at http://127.0.0.1:8765" each time; the carrier stayed connected throughout |
| 16:05:3x | the watches' budget | each exited 5: "relay unreachable … for 15 minutes — the watch ended; run it again when the relay is back". At least nine were armed again within a minute, the relay still down |
| 16:07 | `fabric-secrets relay restore` of the 15:51:56 revision into an empty directory | 29 s, integrity ok; seq 1..856 538, 856 533 messages, 38 consumer cursors, 203 094 events; the cursors' dump hashes identically to the stopped original's |
| 16:08:24 | relay started — not by the drill | on the original database, by `ensure_relay` (`tools/fabric/gzcoord/inbox_parts/relay.py`), which the coordinator's watch runs on the hosting account; that watch had been re-armed because the watch-on-stop hook (`runtime/claude-code/hooks/watch-on-stop.py`) demands one |
| 16:08–16:12 | after | seq continued 856 539 at 16:08:27, no gap; 211 messages by 16:12:42; `fabric-ctl all ping` answered from all 30 accounts |
| 15:50–16:08 | the work | 3 commits on origin (InterWeave); no message was handed to the owner for the human relay |

Neither probe is on the relay: `gzcoord-send` exits 3 with the file's id kept, and nothing retransmitted them.

## What it decides

- **Nothing in the relay's record was lost.** A copy of the stopped database restores whole, its seq and cursors identical to the original, and the relay's seq continued without a gap after the restart.
- **Sessions continued from artifacts** for 18 minutes, at a rate (3 commits) a throttled fleet cannot compare with its hour before. That is not the hour §7 asks for, and step 2 is not done.
- **The human relay was not needed in 18 minutes**, so it was not exercised.

## What broke

Each goes to the role that owns the surface.

1. **The relay does not stop on SIGINT** within 10 s; every stop is an abort with a core dump. SQLite survived it here.
2. **`gzcoord-send` says "not sent" when the carrier accepted.** The exit status follows the relay alone (ADR-064 rule 11), but the line tells the sender to resend or hand the message to the owner, when its addressee already has it.
3. **A watch never shows the carrier's arrivals while the relay is unreachable.** The relay fetch's error is raised before `iw.unseen()` is read (`tools/fabric/gzcoord/inbox_parts/watch.py`), so a second carrier that delivers adds nothing to a session during the outage it exists for.
4. **The watch-on-stop hook re-arms a watch that ended on an unreachable relay**, so every session spins a 15-minute watch per turn while the relay is down. On the hosting account the same re-arm **restarts the relay**, which a drill or an operator's deliberate stop cannot then hold.

## Not verified

- An hour down. The drill ended at 18 minutes, by item 4.
- The relay serving a restored copy with the control agents on it (`fabric-ctl all ping` against a restore), the item left open on 2026-10-27; the copy was restored but the relay came back on the original.
- The human relay under a drill.
- Whether devex-tooling's session was shown the carried probe once the relay was back.

## Since 2026-10-27

The open item "the timer's scheduled runs" is closed: `agent-fabric-relay-backup.service` ran at 21:04 on 11-04 and 03:01, 09:07 and 15:06 on 11-05 (CET), each uploading and finishing (`journalctl --user -u agent-fabric-relay-backup.service`).
