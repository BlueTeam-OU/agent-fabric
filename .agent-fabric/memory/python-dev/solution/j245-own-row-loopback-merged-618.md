---
role: "python-dev"
class: solution
topic: "j245-own-row-loopback-merged-618"
description: "fabric-ctl own-account row answered in-process by the operator's agentd (#618); wait_sent same-chunk reply drop; defer names the raising head; read-back only on operator account; false stderr line = j249"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 147439e6716332fa
---

## fabric-ctl own-account row answered in-process by the operator's agentd (#618); wait_sent same-chunk reply drop; defer names the raising head; read-back only on operator account; false stderr line = j249

#618 (j245, merged 2026-11-15, 2 work 1 fix): control_link loops the operator's own address back to agentd's own handler, reply goes to the waiting ctl session; no child, no roster row. Chosen over a second socket route to keep one accept/replay/signature decision.

- Session.wait_sent dropped a reply arriving in the same recv chunk as sent-all; fixed with its own test (found under parallel load).
- `fabric-pr arm --defer` names the finding by the head that raised it (ee3addac:F2), not the current head.
- Boundary PR (ctl/presence/queue) at 2 work needed the coordinator's AUTHORIZES for the head.
- ADR-029 rule 18 amendment deferred to the coordinator's j832.

**Why:** the relay carried the own row alone (628 of 628) and gate 3 (InterWeave-only) would lose it.

**How to apply:** the live read-back cannot run from a non-operator login (`fabric-ctl all ping` refuses "not a host operator"); ask the operator account, with CLAUDE_BRIDGE_URL=http://127.0.0.1:9 for relay-down. It showed a false stderr line "agentd closed the connection; the relay carries alone" after an all-InterWeave run: j249. Close a merged-PR job with `fabric-jobs done <id> owner/repo#N`.

*Observed 2026-11-15 (python-dev)*
