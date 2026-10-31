---
role: "fabric-coordinator"
class: workflow
topic: "switch-to-named-job-directly"
description: "when the owner names the next job, or a waiting delivery does (a supplier blocked on me), run `fabric-jobs switch <id>` at once; a bare switch activates its own pick, and leaving that costs a pause plus a memory change"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d626da929c5d2f70
---

## when the owner names the next job, or a waiting delivery does (a supplier blocked on me), run `fabric-jobs switch <id>` at once; a bare switch activates its own pick, and leaving that costs a pause plus a memory change

2026-10-30: the owner said "then move to the next interweave job". A bare `fabric-jobs switch` after closing #429's
jobs made j414 (agent-fabric, normal) active although j455 (interweave, high) was queued. `switch j455` then refused
until j414 was paused (pause takes a reason), and switch refused again because the memory directory had not changed
"during j414". Naming the job on the first switch avoids both: `fabric-jobs switch <id>`, then `fabric-fresh --job <id>`.
Related: [[park-a-job-block-not-pause]], [[job-in-other-repo-needs-fresh-session]].

2026-10-31, the same cost a second time: j449 blocked, a bare switch made j452 active, and the watch then delivered
python-dev-03's #435 request (j419, a supplier waiting on me). Leaving j452 again took a pause with a reason plus this
memory change. Before a bare switch, read the watch's latest output and any waiting delivery: a request someone is
blocked on names the next job, so `switch <that id>`.

*References: job-in-other-repo-needs-fresh-session, park-a-job-block-not-pause*

*Anchors: `tools/fabric/jobs.py::switch`*

*Observed 2026-10-30 (fabric-coordinator)*
