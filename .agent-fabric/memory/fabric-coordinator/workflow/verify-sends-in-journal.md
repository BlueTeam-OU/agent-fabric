---
role: "fabric-coordinator"
class: workflow
topic: "verify-sends-in-journal"
description: "A plan or summary saying requests were 'routed' is not a send: read back my journal (fabric-history) before telling the owner work was routed"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 090e49f8e1c202fb
---

## A plan or summary saying requests were 'routed' is not a send: read back my journal (fabric-history) before telling the owner work was routed

2026-10-10: a session summary said the memory corrections had been "routed by author";
the plan I put to the owner repeated it. My journal held no such message and no author
had a job; the requests went out only hours later, after a read-back.

**Why:** compaction summaries and my own plans record intent as if it were done; the
owner decides from what I report.

**How to apply:** before stating that a request, reply or assignment was sent, check
`fabric-history <subject words> --since <day>` (my outbound rows) and the assignee's
`fabric-ctl <login> jobs`. Related: [[request-needs-a-job]].

*References: request-needs-a-job*

*Observed 2026-10-10 (fabric-coordinator)*
