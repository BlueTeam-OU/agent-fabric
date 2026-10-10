---
role: "devex-tooling"
class: domain
topic: "find-is-bfs-not-gnu-findutils"
description: "`find` on develop-qzapp is bfs, which rejects relative timestamps — and the error reads as \"zero results\" whenever stderr is discarded."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 07ee988391b0bc10
---

## `find` on develop-qzapp is bfs, which rejects relative timestamps — and the error reads as "zero results" whenever stderr is discarded.

`find` on this host resolves to **`bfs`**, not GNU findutils. It accepts only
ISO-8601 timestamps:

    find DIR -newermt "1 day ago"      # bfs: error: Invalid timestamp.
    find DIR -newermt "2026-09-06"     # works

The trap is not the error, it is the shape of the failure. The usual
`2>/dev/null` on an exploratory `find | wc -l` turns the rejection into a
confident **`0`**, which reads as a real measurement. It produced a wrong
factual claim in a report this way (reported "0 files touched in 7 days" for a
directory being written that minute).

Rule: when a `find` count looks surprisingly like zero, re-run it without
`2>/dev/null` before believing it. Same class as
[[gpg-signing-needs-a-tty-this-shell-lacks]] — a tool failing in the direction
that looks like a valid answer.

*References: gpg-signing-needs-a-tty-this-shell-lacks*

*Observed 2026-09-15 (devex-tooling)*
