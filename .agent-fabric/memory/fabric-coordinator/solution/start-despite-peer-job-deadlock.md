---
role: "fabric-coordinator"
class: solution
topic: "start-despite-peer-job-deadlock"
description: "a job re-pointed onto a peer's job that waits on this very start (j723/j107) — start it with fabric-jobs start --despite, not by unblocking"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7f18d466ed9af868
---

## a job re-pointed onto a peer's job that waits on this very start (j723/j107) — start it with fabric-jobs start --despite, not by unblocking

A `request:` blocker re-pointed (ADR-037 rule 8) onto a peer's `job:<login>/j<n>` can deadlock when that peer job
waits on the requester's own next step (j723 → python-dev-04/j107, which needed my push). Fixed by python-dev-03's
j127, BlueTeam-OU/agent-fabric#553 (fd24a141, merged 2026-11-11): `fabric-jobs start <id> --despite job:<login>/j<n>
"<why>"`. Only when every unmet blocker is another login's `job:` blocker and each is named; the log keeps each
waived blocker's state and the reason; `switch` never waives. A plain refused start prints the exact command.
Not yet in ADR-037 text or policies/agent-jobs/SKILL.md: that is my j739 (its target branch, the j127 one, has
merged, so it needs its own branch). Closed my j731 with #553.

*Anchors: `tools/fabric/jobsparts/needs.py::_blockers_cleared`, `tools/fabric/jobsparts/needs.py::--despite waives a job: blocker of another login only`*

*Observed 2026-11-11 (fabric-coordinator)*
