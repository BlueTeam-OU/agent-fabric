---
role: "devex-tooling"
class: solution
topic: "arm-authorization-beside-owner-word"
description: "fabric-pr arm with the owner's word in --basis used to drop a given --authorization unread (no head check); from j271 it is read as the relayed word, head-bound, no role check"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4f3b2ac1296429ee
---

## fabric-pr arm with the owner's word in --basis used to drop a given --authorization unread (no head check); from j271 it is read as the relayed word, head-bound, no role check

Until j271 (commit 7027f0e6, 2026-11-02), `fabric-pr arm N --basis "the owner's word …" --authorization <id>` under the minimum printed "no authorization is needed: … not read, and not recorded": the AUTHORIZES head in fabric-coordinator's relaying DECISION was checked by nobody (gzapi-org/[redacted]-shop-transit#4, domain-transit checked it by hand). Now verify_grant reads it with role "" (the owner holds no role): addressed TO the session, another login, DECISION/REPLY, repo#num@head; refusals only, comment says "The owner's word relayed by <login> (<mid>)". The basis alone still arms; a fleet policy with no below_min_authority still does not read an --authorization without the owner's word. Related: [[gate-relaxing-marker-trusted-structured-head]], [[below-minimum-arming-reasons-accepted]].

*References: below-minimum-arming-reasons-accepted, gate-relaxing-marker-trusted-structured-head*

*Anchors: `tools/fabric/github/arm.py::elif authorization and under`*

*Observed 2026-11-02 (devex-tooling)*
