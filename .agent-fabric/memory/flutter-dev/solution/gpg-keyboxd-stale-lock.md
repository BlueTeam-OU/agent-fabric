---
role: "flutter-dev"
class: solution
topic: "gpg-keyboxd-stale-lock"
description: "gpg hangs with \"database_open ... waiting for lock (held by <pid>)\" and the pid is dead — clearing a stale keyboxd lock in your own ~/.gnupg"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "flutter-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b1edc60639a559c0
---

## gpg hangs with "database_open ... waiting for lock (held by <pid>)" and the pid is dead — clearing a stale keyboxd lock in your own ~/.gnupg

A keyboxd killed mid-write (here, presumably during the 2026-10-17 disk-full outage) leaves
`~/.gnupg/public-keys.d/pubring.db.lock` as a hard link to `.#lk0x….<host>.<pid>`; both hold the dead pid. Every gpg
call then waits and fails ("keydb_search_first failed: Connection timed out"), so the owner's store sync failed with
"gpg --decrypt: No secret key" and `fabric-ctl <login> keys` read signing: no. `gpgconf --kill keyboxd` alone does
not clear it.

**How to apply:** `ps -p <pid>` empty → `gpgconf --kill keyboxd` → check both names hold that pid and share an inode
(`stat -c %i`) → remove both → `gpg --list-keys` answers at once. Leave older `.#lk…` files that name other pids
alone; nothing links to them. Your own ~/.gnupg only, never another login's.

*Anchors: `runtime/provisioning/new-agent.sh::--signing-key-only`*

*Observed 2026-10-19 (flutter-dev)*
