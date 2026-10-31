---
role: "fabric-coordinator"
class: workflow
topic: "digest-trim-keeps-lookups"
description: trimming a DIGEST entry to fit 250 words — diff its word set against main and look up every word that left, before committing
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2b061f281d272e7d
---

## trimming a DIGEST entry to fit 250 words — diff its word set against main and look up every word that left, before committing

Trimming an ADR's DIGEST entry to stay under `DIGEST_ENTRY_WORDS` (250,
`tools/fabric/adr.py`) silently drops lookup keys. 12424efe trimmed
ADR-022's keywords line, and `fabric-adr lookup Monitor` stopped finding
ADR-022 (#416 review F5). Also lost: --follow, defaultMode, resume,
planning, and "switch" from a body line. Fixed in 6fd8dd51.

**Why:** `adr check` counts words only. It cannot tell a cut article
from a cut lookup key, and the review is the first thing that notices.

**How to apply:** before committing a DIGEST edit, compute the entry's
word set on origin/main minus the new one (a short python over
`git show origin/main:docs/adr/DIGEST.md`). Run `adr.py lookup` on each
word that left. Cut words by shortening rule refs (`§5 rules 1–3` →
`§5 r1–3`) and dropping articles. Drop a keyword only when the word is
already in the entry's body, so the word set loses nothing (9ea09415 on
#433 did that for ADR-037: the word set lost nothing).

Each amendment needs its own DIGEST bullet, two on one day included:
`adr check` matches the bullets' dates to the history file one to one,
so merging the two into one line fails.

Related: committing on a for/ branch for a job whose recorded worktree
is another branch's: the one-job guard refuses a commit in a new
worktree. Check the for/ branch out in the job's recorded copy (the main
checkout here), commit, push, and return it to main
([[holder-checkout-back-to-main]]).

*References: holder-checkout-back-to-main*

*Anchors: `tools/fabric/adr.py::DIGEST_ENTRY_WORDS`*

*Observed 2026-10-30 (fabric-coordinator)*
