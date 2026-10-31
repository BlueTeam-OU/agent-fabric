---
role: "fabric-coordinator"
class: workflow
topic: "block-on-job-not-request-after-reply"
description: "fabric-jobs block --on-request clears once the assignee REPLYs \"undertaken\"; block on job:<login>/<jid> to wait for the work itself"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - cc6e2fa1b5172cfe
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

*Anchors: `tools/fabric/jobsparts/verbs.py::--on-request`*

*Observed 2026-10-22 (fabric-coordinator)*
