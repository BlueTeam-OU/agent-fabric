---
role: "python-dev"
class: workflow
topic: "j168-carrier-install-merged-375"
description: "j168 carrier install merged (#375); rule 14 shape, process check via /proc exe, arm-needs-retry, suite red from host load, fix-vs-carry call"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5986f82c68dcef97
---

## j168 carrier install merged (#375); rule 14 shape, process check via /proc exe, arm-needs-retry, suite red from host load, fix-vs-carry call

#375 merged 2026-10-25 on the owner's word: control/carrier_install.py (install + read, rule 14: restart the running units, check MainPID /proc/<pid>/exe not "(deleted)", every reported program's --version, carrier status; failure restores the kept programs). Names come from gzcoord.carrier CARRIER_NAME/LABEL (lint: no generic file names the project).

**Why:** the coordinator's rule 14 text moved twice during the PR (a contract change arrived by REPLY to an earlier session; the merge of main brought the final text); a P3 that deviates from the owner's rule text is fixed, not carried.
**How to apply:** read the thread (`fabric-history --thread`) at session start for contract changes; a first `fabric-pr arm` on a CLEAN PR can end "idle" (auto-merge refused in clean status): run it once more and it reads MERGED. A full suite under load average ~100 ends red on 900 s budgets and relay-watch timeouts: say so in the arm basis with CI green as the evidence, and never restart it mid-review (each head change costs a lease wait of an hour). The commit hook refuses commits from a sibling worktree: move the branch into the main checkout for the commit, then switch main back (the coordinator's upgrade skips an account whose checkout is off main). See [[job-hook-commit-in-main-checkout-works]].

*References: job-hook-commit-in-main-checkout-works*

*Observed 2026-10-25 (python-dev)*
