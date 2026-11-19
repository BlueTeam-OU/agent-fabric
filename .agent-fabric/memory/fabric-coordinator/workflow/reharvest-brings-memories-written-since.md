---
role: "fabric-coordinator"
class: workflow
topic: "reharvest-brings-memories-written-since"
description: "Re-harvesting one account to answer a drain review also brings in memories written since the drain; check each new claim against main and --hold one that describes an open PR"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: gzapp.decks
    working_copy: gzapp.decks
derived_from:
  - 79f051ee1369d7e0
---

## Re-harvesting one account to answer a drain review also brings in memories written since the drain; check each new claim against main and --hold one that describes an open PR

A drain PR's review findings are corrected at source by the author. The
corrected text then reaches the corpus through a fresh harvest
(`fabric-ctl <login> memory --out <dir>`), assembled at the drain's own
stamp. That harvest also carries every memory the author wrote after the
drain, and those were never part of the drain or its review.

Seen 2026-11-09 on gzapp.decks #29 (job j660, commit 03f2bb3). The
re-harvest of brand-comms-01 held the six corrected claims plus two new
ones. One new claim (manrope-liga-and-typographer-rewrite-text) said
`scripts/doc.py` "now" disables replacements, but that change was only
on the open gzapp.decks#37, and lint flagged its anchor stale-hard. It
was held with `assemble.py --hold` (a JSON list of
`brand-comms/solution:<topic>`), which keeps the watermark below it so
the next drain writes it.

**How to apply:** diff the old and new bundles' claims by
(class, topic) before assembling. For each claim the review did not ask
for, read its anchors against main. Hold any claim whose facts sit on an
unmerged branch. Lint at origin before committing. Also see
[[drain-fabric-worktree-beside-projects]]: a re-run needs the fabric
worktree beside the projects again.

Also from that run: when a memory's title changes between two passes at
the same stamp, the assembler keeps the earlier section as a second
section of the slice. A `merge_target` on the memory replaces only the
one section it names. The leftover section has no source and is removed
by hand, the same way as an orphan slice.

*References: drain-fabric-worktree-beside-projects*

*Anchors: `agent-fabric:tools/fabric/assembler/intake.py::hold_back`*

*Observed 2026-11-09 (fabric-coordinator)*
