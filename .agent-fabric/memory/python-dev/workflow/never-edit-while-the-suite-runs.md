---
role: "python-dev"
class: workflow
topic: "never-edit-while-the-suite-runs"
description: "tests/run.sh reads each suite's files when it reaches it; an edit made mid-run is what a late section tests — a green that never covered the pushed head"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a29c274da9d6de9f
---

## tests/run.sh reads each suite's files when it reaches it; an edit made mid-run is what a late section tests — a green that never covered the pushed head

2026-10-09, #132: the full suite ran on head 2deb1446 for ~45 min; meanwhile I edited
communication/gzcoord/tests/i18n.test.mjs to fix a CI failure. The gzcoord section runs last, read the edited file,
and passed 34/34 — while the pushed head failed it (CI red, and `tests/run.sh gzcoord` on a stash reproduced it).
The same run also never saw the httpsafe import break the i18n fixture, because CI was not read before the review loop.
**Why:** a suite result is evidence only for the tree it read from start to end; a mid-run edit makes it neither the
old head's nor the new one's.
**How to apply:** while a full run is going, edit nothing in that worktree (fix in a second worktree, or wait); read
`pr-gate.sh` / the CI run of the pushed head before starting a review loop, so red checks are fixed in the same round.
Related: [[review-before-suite-and-numeric-guards]], [[suite-red-check-df-first]].

*References: review-before-suite-and-numeric-guards, suite-red-check-df-first*

*Observed 2026-10-09 (python-dev)*
