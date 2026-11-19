---
role: "fabric-coordinator"
class: solution
topic: "own-job-blocker-never-clears"
description: "a job: blocker on the asker's OWN job that came from someone else's REQUEST — fixed by #543; how it is read now"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 61058cd1506433a3
---

## a job: blocker on the asker's OWN job that came from someone else's REQUEST — fixed by #543; how it is read now

Fixed: BlueTeam-OU/agent-fabric#543 (python-dev-02 j134, merged 2026-11-10, 30886b51).
`job:<me>/j<n>` is now read from this login's own list (`_from_own_list` in
tools/fabric/jobsparts/blockers.py): done/dropped/delivered clear, an open state waits, absent
follows the peer's absent rule — never through job-state, which answers only the REQUEST's
sender and used to refuse the holder for ever. Read back live 2026-11-10 (j734): own done job
→ cleared, own active job → waiting. The old workaround (`block <id> "owner: <text>"`, then
`start`) is no longer needed. Reported by rust-ui-dev-01 (j232 on j229); told it landed.
A peer's job is still asked through job-state: [[peer-job-blocker-operator-only]].

*References: peer-job-blocker-operator-only*

*Anchors: `tools/fabric/jobsparts/blockers.py::def _from_own_list`, `tools/fabric/control/jobs.py::job-state answers the sender`*

*Observed 2026-11-10 (fabric-coordinator)*
