---
role: "fabric-coordinator"
class: solution
topic: "launcher-ff-second-fetch"
description: "\"cannot fast-forward (local commits or changes)\" on a clean, behind checkout — the old launcher's second fetch, fixed by #547"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e71c4a31cadb2e5f
---

## "cannot fast-forward (local commits or changes)" on a clean, behind checkout — the old launcher's second fetch, fixed by #547

A launcher refusal "agent-fabric is N commit(s) behind origin/main and cannot
fast-forward (local commits or changes)" on a clean checkout was the launcher
judging from one fetch, then running `git pull --ff-only origin main`, which
fetched again; a failure of that second network step fell back to the generic
text with git's stderr dropped. `fabric-ctl upgrade` merges the fetched ref, so
it worked at once. Fixed by python-dev-01 in BlueTeam-OU/agent-fabric#547
(merged 2026-11-10, 5c3c3af5): `tools/fabric/launcher/currency.py` runs
`merge --ff-only origin/main` and the refusal carries git's last stderr line.
Which failure the 2026-11-09 python-dev-03 relaunch hit was never measured.
`runtime/provisioning/moveto/moveto.py` still pulls, but with no prior fetch
and with the reason printed — not the same defect. Closed j695.

*Observed 2026-11-10 (fabric-coordinator)*
