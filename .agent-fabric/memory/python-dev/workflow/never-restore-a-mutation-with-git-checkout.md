---
role: "python-dev"
class: workflow
topic: "never-restore-a-mutation-with-git-checkout"
description: planting mutations on uncommitted work — restore from a copy, never git checkout/stash of the file
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d60e49e30a9f1a7b
---

## planting mutations on uncommitted work — restore from a copy, never git checkout/stash of the file

Planting a mutation and restoring with `git checkout -- <file>` returns the
file to HEAD, discarding every uncommitted edit in it; on an untracked file
it fails and leaves the mutation in place. Lost secret_store.py's edits
once this way (j49, 2026-10-07).
**Why:** mutation runs happen before the commit, on exactly the edits a
checkout throws away.
**How to apply:** commit first and mutate the committed state, or `cp file
bak; mutate; run; cp bak file` — never git as the restorer. See
[[test-port-by-mutation-parity]].

*References: test-port-by-mutation-parity*

*Observed 2026-10-07 (python-dev)*
