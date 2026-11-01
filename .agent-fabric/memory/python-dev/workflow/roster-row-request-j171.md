---
role: "python-dev"
class: workflow
topic: "roster-row-request-j171"
description: "gzcoord-carrier roster-row run from the main checkout prints the signed row JSON; reply carries it whole"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 09276228a513172a
---

## gzcoord-carrier roster-row run from the main checkout prints the signed row JSON; reply carries it whole

j171 (2026-10-25): `gzcoord-carrier roster-row` in the main agent-fabric checkout exited 0 and printed a JSON object (agent_id, endpoint, identity_show, login, login_signature, peer_id). Redirect it to a scratchpad file, check it parses, then splice it unchanged into the REPLY body (gzcoord-compose, fill with python, gzcoord-send). No secret in it.

**Why:** the coordinator admits the row with a port and countersigns it; a REPLY with a reformatted row would not verify.
**How to apply:** `fabric-jobs switch` refuses while a REPLY-EXPECTED request from the same sender is unanswered, so acknowledge a newly queued follow-up request (name the branch) before switching. Follow-on: [[ledger-p1-supply-state]] style jobs; next was j172 (carrier start/stop actions).

*References: ledger-p1-supply-state*

*Anchors: `tools/fabric/gzcoord/carrier/main.py::roster-row`*

*Observed 2026-10-25 (python-dev)*
