---
role: "fabric-coordinator"
class: threads
topic: "j433-relay-down-drill-plan"
description: "j433 plan (ADR-034 §7 step 2): relay down one working hour; stop gzcoord-relay.service on my account, back up the quiescent db, come back on a restored copy so fabric-ctl all ping against a restore is shown; owner picks the window"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 21755c61849800d7
---

## j433 plan (ADR-034 §7 step 2): relay down one working hour; stop gzcoord-relay.service on my account, back up the quiescent db, come back on a restored copy so fabric-ctl all ping against a restore is shown; owner picks the window

Drafted 2026-10-28; waits on the owner choosing a working-hour window. The relay is `gzcoord-relay.service`, a user unit on my own login (user). It listens on 127.0.0.1:8765, with `--db %h/projects/.gzcoord/claude-bridge.db` in ExecStart and its log in `bridge.log` beside the db.

**Steps:**
1. **Before.** Run `fabric-ctl all status` and `fabric-ctl all jobs` as the baseline. Note the relay's last seq. Count the commits and pushes across the fleet in the hour before. Broadcast an INFO with the window, saying that work continues from artifacts (git, PRs, job lists) and that a message that must go reaches the owner, who relays it by hand.
2. **Down.** `systemctl --user stop gzcoord-relay.service`. Then run `fabric-secrets relay backup` on the now-quiescent db, so the copy is complete. `--verify` it.
3. **The hour.** Observe and record:
   - what `gzcoord-send` does (refuses or leaves the message pending; a bypassed send marked failed);
   - what inbox watches do (exit with a reason, or wait);
   - `fabric-ctl` refusing;
   - the deck and agentd;
   - whether agents keep committing (the same count as before);
   - every human-relayed item.
4. **Back on a restore.** Restore the backup into an empty directory, add a drop-in overriding ExecStart's `--db` to that copy, and start the relay. The original db stays untouched as the fallback. Then:
   - `fabric-ctl all ping` must answer from every account;
   - `gzcoord-inbox --replay` shows the past;
   - the pending sends from the hour arrive, and nothing is lost: seq continues, and nothing a sender queued is missing.

   This closes the open item in the 2026-10-27 live check: ping against a restored relay. Then either keep the restored db as the live one or move back to the original. Decide on the day, and remove the drop-in if moving back.
5. **Read-back** to `docs/live-checks/<date>-relay-down-drill.md`: what was measured, what broke, and what follows. Then amend ADR-034 §7: step 2 is done.

**Risks:**
- The 6-hourly backup timer may fire during the hour. A run against a stopped relay should still read the file; check that before starting.
- Agents waiting on a REPLY may stall. That is part of what the drill shows.

*Observed 2026-10-28 (fabric-coordinator)*
