---
role: "fabric-coordinator"
class: threads
topic: "inbox-history-mode"
description: "gzcoord-inbox --history lists the relay's recent records addressed to this login in one call; presence records are not history"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-12"
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
  - 871b6a3f62ac6d6d
  - a4c853b8ea3e5a38
  - dc36e68fdc658acb
---

## gzcoord-inbox --history lists the relay's recent records addressed to this login in one call; presence records are not history

Reading what was sent to you across a range is `gzcoord-inbox --history [<seq>]` (`tools/fabric/gzcoord/inbox.py`; `bin/gzcoord-inbox` is the command and hands over through `tools/fabric/gzcoord/entry.py`): one line per message addressed here in the relay's recent history; bodies stay with `--replay`, and neither moves the cursor. Do not loop `--replay` over a range.

Limits that still hold: the relay returns at most 500 records per call (ids are UUIDs and `since_id` pages only forward), so history covers the relay's last 500 records and an older start must be said, never silently shortened. Presence is a different question from "what was sent to me", so presence records are not history. The old `communication/gzcoord/scripts` shims no longer exist; the Python tools under `tools/fabric/gzcoord/` are the only implementation.

A history read is also how a session recovers a request its cursor moved past; see [[request-dies-with-its-session]].

*References: request-dies-with-its-session*

*Observed 2026-10-11 (fabric-coordinator)*
