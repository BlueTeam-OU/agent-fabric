---
role: "fabric-coordinator"
class: threads
topic: "inbox-history-mode"
description: "gzcoord-inbox --history and --replay read the account's journal too since #581 — journal first for a MESSAGE-ID, journal-only rows after the relay's list"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - 41aca8ba08f539bb
  - 510061c5ad37fa79
  - 871b6a3f62ac6d6d
  - a4c853b8ea3e5a38
  - dc36e68fdc658acb
---

## gzcoord-inbox --history and --replay read the account's journal too since #581 — journal first for a MESSAGE-ID, journal-only rows after the relay's list

Since agent-fabric #581 (merged 2026-11-13), `gzcoord-inbox --replay <MESSAGE-ID>` answers from the account's own journal first (read-only, `episodic.open_readonly`) in every configuration; a relay seq or an id the journal lacks goes to the relay's newest 500. `--history [<seq>]` prints the relay's list, then "in your journal, not in the relay's page (carried another way)" for journal-only rows; with no relay configured, no token, or a failed relay read, it lists the journal alone. The seq filter is the carrier's seq, so a carrier-only row (no seq) shows only without one. An unreadable journal is exit 1, never "absent". Code: `tools/fabric/gzcoord/inbox.py` replay/history dispatch, `inbox_parts/records.py`. Read back live 2026-11-14 (--history showed both sections). Skill text updated in j815 (gzcoord-receive §3). Bodies stay with `--replay`; never loop `--replay` over a range; presence is not history.

*Observed 2026-11-13 (fabric-coordinator)*
