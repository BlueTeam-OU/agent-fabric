---
role: "devex-tooling"
class: domain
topic: "amend-records-only-staged-changes"
description: "git commit --amend -F - without -a re-records the message only; an edit made after the commit stays unstaged — check git status before pushing an amend"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 11f4f36aa645d012
---

## git commit --amend -F - without -a re-records the message only; an edit made after the commit stays unstaged — check git status before pushing an amend

2026-10-04, InterWeave supply provenance-step: I edited ci.yml after the
commit, then `git commit -q --amend -F -` to add the Supplier-Review trailer
claiming the fix — the edit was unstaged, so 1426e3c4 went out with the old
text and a false trailer. Fixed by a follow-up commit (9ed83faf) and a
corrected HANDOFF; no force push.

**Why:** amend takes the index, not the working tree; the trailer then lies.

**How to apply:** `git add` (or `-a`) before an amend, and `git status
--short` must be empty before any push that follows a commit claiming a fix.

*Observed 2026-10-04 (devex-tooling)*
