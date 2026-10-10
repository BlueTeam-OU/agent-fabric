---
role: "python-dev"
class: workflow
topic: "stale-keyboxd-lock-after-reboot"
description: "commit signing hangs \"database_open waiting for lock (held by N)\" — a keyboxd lock from before a reboot; check pid and boot time, then remove"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e4ba4f56f9148c7c
---

## commit signing hangs "database_open waiting for lock (held by N)" — a keyboxd lock from before a reboot; check pid and boot time, then remove

Seen 2026-10-08: every signed commit failed with "gpg: Note: database_open
... waiting for lock (held by 4067)" / "keydb_search failed: Connection timed
out" / INV_SGNR. ~/.gnupg/public-keys.d/pubring.db.lock (and its
.#lk0x...<host>.<pid> hardlinks) dated 2026-10-05, PID gone, host booted
2026-10-08: keyboxd does not break a lock whose holder died before a reboot.
Fix: confirm `ps -p <pid>` empty and `uptime -s` after the lock's mtime, rm
pubring.db.lock and the .#lk* files, `gpgconf --kill keyboxd`, test with
`echo x | gpg --batch --clearsign --local-user <fpr>`. Abort a half-applied
rebase first (git rebase --abort).

*Observed 2026-10-08 (python-dev)*
