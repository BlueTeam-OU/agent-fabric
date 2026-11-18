---
role: "fabric-coordinator"
class: solution
topic: "peer-job-blocker-operator-only"
description: "a non-operator's job:<peer>/jN blocker — read through public job-state since #527, answered only to the REQUEST's sender; any other waiter stays unknown by design, so re-block on pr:/clock"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 58fbac9f5928a114
---

## a non-operator's job:<peer>/jN blocker — read through public job-state since #527, answered only to the REQUEST's sender; any other waiter stays unknown by design, so re-block on pr:/clock

Before #527 (merged 2026-11-09, a4b54d78), blockers.py read a peer's board only through the
operator-only `jobs` op, so a non-operator's `job:<peer>/jN` blocker read unknown forever (devex-tooling's
j306 was re-pointed into a cycle that way). Since then a non-operator asks the peer's public `job-state`
op, which answers one job's state only to the sender of the REQUEST it was taken from (ADR-037 §5 rule 8).
Live read-back docs/live-checks/2026-11-09-peer-job-state-read.md: p2p-network-dev-02/j103 on user/j698
read "waiting / queued"; ux-designer-01/j95 on rust-ui-dev-01/j213 (not its request) read unknown with
the refusal in its detail. A waiter that is not the sender still needs `fabric-jobs block <id> --on pr:…`
or `clock:<a minute ahead>` (a second block replaces the blockers). Read a stuck agent's screen first
([[stuck-agent-read-its-pane]]).

*References: stuck-agent-read-its-pane*

*Anchors: `tools/fabric/jobsparts/blockers.py::read_board`, `tools/fabric/control/ops/__init__.py::PUBLIC_OPS`, `tools/fabric/control/jobs.py::job_state`*

*Observed 2026-11-09 (fabric-coordinator)*
