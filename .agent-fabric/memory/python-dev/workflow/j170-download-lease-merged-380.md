---
role: "python-dev"
class: workflow
topic: "j170-download-lease-merged-380"
description: "j170 download lease merged in #380; arm traps (job hook, AUTHORIZES), fabric-review next prerequisites"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c9ad344a54565aa4
---

## j170 download lease merged in #380; arm traps (job hook, AUTHORIZES), fabric-review next prerequisites

#380 merged 2026-10-25 (1 work + 1 fix, boundary under 8, armed with coordinator's AUTHORIZES id via --authorization). Coordinator records 2668 s in ADR-029 rule 12 on its next branch.

**Traps:** (1) after `fabric-jobs deliver` the job leaves active and the hook refuses `fabric-pr arm`; `fabric-jobs start <id>` re-activates it, then arm, then deliver/sweep. (2) `fabric-review next` needs `fabric-review save <pr> 1 < report` first, `repository:` a local path in the request, `range:` sha..sha, and `--pr` not `--report`. (3) the stripped suite's `test_jobs.py` can hit its 900 s budget under load ~35; it passes alone in ~3.5 min.

*Observed 2026-10-25 (python-dev)*
