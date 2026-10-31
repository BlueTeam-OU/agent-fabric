---
role: "fabric-coordinator"
class: workflow
topic: "checks-need-a-control"
description: "A survey or live check that reports all-pass needs a control that can fail and captured evidence before I relay it; a cause I name in another lane is a hypothesis with a control changing only the suspected factor"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ef19f0d1cf5ba253
---

## A survey or live check that reports all-pass needs a control that can fail and captured evidence before I relay it; a cause I name in another lane is a hypothesis with a control changing only the suspected factor

I relayed "all 11 pass" from a scan with no positive or negative control; 8 were refused when tried. I retracted a "52 of 53" figure. In other lanes I named causes that the owners disproved: a sighting that predated a fix on main, an inbox watch blamed for what was start-up timing.

**Why:** a check that cannot fail and a cause stated as fact both send others down the wrong path.
**How to apply:** include one case that must fail and one that must pass, keep the output, and spot-check on a real account. When reporting another lane's failure, check it against current main and send the cause as a hypothesis with its control. Related: [[suite-verdict-not-pipeline-exit]], [[verify-sends-in-journal]].

*References: suite-verdict-not-pipeline-exit, verify-sends-in-journal*

*Observed 2026-10-22 (fabric-coordinator)*
