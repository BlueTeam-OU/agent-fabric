---
role: "python-dev"
class: solution
topic: "wait-merged-pending-j53"
description: "wait-merged \"could not read checks\" on pending was not reproducible on main; what #284 changed; gh --json exits 0 on pending"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b87e397bfb7f6e2d
---

## wait-merged "could not read checks" on pending was not reproducible on main; what #284 changed; gh --json exits 0 on pending

gh 2.87.3 `pr checks --json` exits 0 even with pending/failed checks (measured on #283); wait_merged.required_checks already read stdout on non-zero, so the #126 sighting predates #128. #284 adds `checks pending: <names>`, a per-read `checks_why` on the unreadable note, and drops the false "blocked, checks still pending" line. Review brief: `python3 tools/fabric/review_brief.py render req.json` (fabric-review brief took no verb); a re-review of a fix range needs `card_base` = first round's base. Post the first review BEFORE pushing fixes.

*Anchors: `tools/fabric/github/wait_merged.py::checks_why`*

*Observed 2026-10-16 (python-dev)*
