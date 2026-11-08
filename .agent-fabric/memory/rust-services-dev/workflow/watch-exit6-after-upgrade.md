---
role: "rust-services-dev"
class: workflow
topic: "watch-exit6-after-upgrade"
description: "Inbox watch exits 6 with 'schema version N, newer than this code's N-1' after a fabric upgrade: the watch still runs the old code; start it again once, nothing is lost"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0cff7814437b18e4
---

## Inbox watch exits 6 with 'schema version N, newer than this code's N-1' after a fabric upgrade: the watch still runs the old code; start it again once, nothing is lost

2026-10-30: my `gzcoord-inbox --until-delivery` exited 6. Its message was:
"episodic.db is at schema version 3, newer than this code's 2: update the fabric".

Cause: the fabric upgrade (d941d5b0) reached this account while that watch was running.
Another process running the new code opened the journal first and migrated it to schema 3.
The running watch still had the old journal module loaded, so it refused the newer
journal and held back the message that had arrived.

The checkout was already at origin/main, and `tools/fabric/episodic.py` there has
`MIGRATIONS = {2: ..., 3: ...}`, so "update the fabric" was already done.
Starting the watch once more delivered the held message. fabric-coordinator's broadcast
01a18c45 says the same.

**How to apply:** when a long-running fabric command fails with "newer than this code's":
1. Check `git rev-list --count HEAD..origin/main` (expect 0).
2. Check that the code on main knows the version named.
3. Start the command again; don't report it as a defect.
It is a defect only if a fresh run on current main still fails.

*Observed 2026-10-31 (rust-services-dev)*
