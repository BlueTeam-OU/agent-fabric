---
role: "fabric-coordinator"
class: solution
topic: "pgrep-f-kills-own-session"
description: "a pgrep/pkill -f pattern can match the session's own claude process (its argv carries the opening prompt); killing by pattern ended architect-cto-01's session twice and mine once"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5e17c145e77f34f5
---

## a pgrep/pkill -f pattern can match the session's own claude process (its argv carries the opening prompt); killing by pattern ended architect-cto-01's session twice and mine once

A claude process launched by the fabric carries its opening prompt in argv for the whole session. Until 0950c4d, that prompt named `gzcoord-inbox --follow`.

`pgrep -f 'gzcoord-inbox --follow' | xargs kill`, run to clear "stale" watchers, matched the session itself and killed it: exit 144, transcript over two seconds later. It happened to architect-cto-01 twice on 2026-09-29, and the owner took it for a failed restart. My own `pkill -f` pattern killed my shell earlier.

**Fixed in 0950c4d:**
- The opening prompt names no command. It points to the session-start hook's NO INBOX WATCH line, which is context, not argv.
- `runtime/claude-code/hooks/self-kill-guard.py` refuses a kill by a pattern that matches the session's own claude command line.
- `fabric-fresh` signals by pid and still works.

**How to apply:**
- Select processes by pid or `pgrep -x`, never by a `-f` pattern, when killing.
- Never kill the inbox watch: a Monitor ends at its expiry.
- In a listing, a line starting with `claude` is the session itself.

See [[one-inbox-watch-after-compaction]].

*References: one-inbox-watch-after-compaction*

*Observed 2026-09-29 (fabric-coordinator)*
