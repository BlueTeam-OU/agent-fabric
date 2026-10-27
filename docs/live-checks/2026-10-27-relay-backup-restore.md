# 2026-10-27 — the relay's database backed up, verified and restored

Run by fabric-coordinator, on develop-qzapp, against the live relay's database (`~/projects/.gzcoord/claude-bridge.db`), with `fabric-secrets relay backup`, `relay backup --verify` and `relay restore` as merged by agent-fabric #404 (tools/fabric/secret_relay.py, tools/fabric/secretstore/relaycopy.py). The question (agent-fabric ADR-034 §7, the first concrete step): can the channel's past be brought back from a copy that the host's loss does not take, and does the restored database serve a session.

## What was measured

| step | result |
|---|---|
| `fabric-secrets relay backup` | 754 962 432 bytes uploaded as 163 508 108 (compressed, encrypted, signed); sha256 `db69f7765b5f4088e055872d078f2351507760494f21d459dfd21acbd650653b`; real 1m39s; revision 2026-10-27T12:32:10Z |
| `fabric-secrets relay backup --verify` | "the revision of 2026-10-27T12:32:10Z decrypts, matches its manifest and passes integrity_check" |
| `fabric-secrets relay restore <empty dir>` | "754962432 bytes of 2026-10-27T12:32:10Z restored, integrity ok" |
| a second claude-bridge on 127.0.0.1:18765 serving the restored database with the live token | answered; `CLAUDE_BRIDGE_URL=http://127.0.0.1:18765 gzcoord-inbox --replay 615662` returned that message, from python-dev-02, sent 2026-10-27T12:18:32Z |

Counts read with sqlite: the copy held 615 969 messages, seq 1..615 974. The live database at that moment held 616 044, seq 1..616 049: the 75 messages since the snapshot, which is the age a copy can have; the schedule is every 6 h, not yet observed.

The test relay was stopped and the restored copy deleted afterwards.

## What it decides

The relay row of agent-fabric ADR-034 §1 no longer loses the channel's past on the loss of the host: it is copied every 6 h (`agent-fabric-relay-backup.timer`, installed by bootstrap on the relay's account only) to Proton Drive, encrypted and signed, and a restore has been read back. That is the first step of §7.

## Not verified

- **`fabric-ctl all ping` against the restored relay.** It needs the accounts' control agents connected to that relay, which is the relay-down drill, §7's second step. The restore was shown to serve the channel's past, not to carry the control plane.
- A restore on another host, or after the loss of the host: the restore ran on the host that holds the database, from the uploaded copy.
- The timer's first scheduled runs: this page records the command run by hand, not the units' firing.
