---
role: "fabric-coordinator"
class: workflow
topic: "block-on-job-not-request-after-reply"
description: "fabric-jobs block --on-request clears once the assignee REPLYs \"undertaken\"; block on job:<login>/<jid> to wait for the work itself"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - cc6e2fa1b5172cfe
  - ff8fde97535b95cf
---

## fabric-jobs block --on-request clears once the assignee REPLYs "undertaken"; block on job:<login>/<jid> to wait for the work itself

2026-10-22, j349: `fabric-jobs block j349 --on-request 01a163f9-…` printed "blocker cleared"
at once, because python-dev-01 had already answered the REQUEST ("taken as j149"), and
`switch` handed j349 straight back. A REPLY answers the request; it does not deliver the work.

**How to apply:** once the assignee has replied, block on the job the request became on their
list — `fabric-jobs block <id> --on job:<login>/<their jid>` (read it from `fabric-ctl <login> jobs`).
That waits until their job is delivered or done. Possibly a fabric-jobs defect, not a decision:
whether `--on-request` should hold until the assignee's job closes is open.

2026-10-30 again (j412): python-dev-01's "taken" REPLY cleared request:01a18bf5, switch then picked j412 over j394 (critical path) though nothing had arrived. The supplier's job id is on its board, not in its REPLY: `fabric-ctl <login> jobs | grep <request id or topic>` (j191 here), then `fabric-jobs block <id> --on job:<login>/j<n>`.

2026-11-05, third time (j526): devex-tooling's "taken as j291" REPLY 01a1aa93-7ad8 cleared request:01a1aa92 and the fresh session was launched for j526 with nothing to fold (for/user/arm-record-path not yet pushed). Bitten three times, so it is a fence now, not a rule: queued as a fabric-jobs change (a request blocker whose REPLY names a job of the assignee's re-points itself to job:<login>/j<n>).

2026-11-05, fourth time (j556): python-dev-02's "taken as j115" REPLY 01a1aa94 cleared request:01a1aa93 and this session was launched for j556 with nothing to fold. Re-blocked on job:python-dev-02/j115. The fence is j618 (queued, to be contracted to a python-dev holder); until it lands, every contract REQUEST is followed the same turn by reading the supplier's board and blocking on job:<login>/j<n>.

2026-11-05: j618 contracted to python-dev-01, REQUEST 01a1aaba-ec41-7349-96a3-134b3e6506ea (board-title match on "(REQUEST <mid>)" first, body j<n> fallback, unknown when neither can be read). ADR-037 rule 8 amendment is mine, as a commit onto their branch. j618 blocked on that request; re-block on job:python-dev-01/j<n> on their REPLY.

*Anchors: `tools/fabric/jobsparts/verbs.py::--on-request`*

*Observed 2026-10-22 (fabric-coordinator)*
