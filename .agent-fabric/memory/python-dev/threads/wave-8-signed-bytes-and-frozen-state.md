---
role: "python-dev"
class: threads
topic: "wave-8-signed-bytes-and-frozen-state"
description: "Wave 8 (j67) revised on #131 — signed bytes are Node JSON.stringify to the byte; persisted state frozen with the wire; no new wire behaviour before Node is deleted"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a965e4010e879a7c
---

## Wave 8 (j67) revised on #131 — signed bytes are Node JSON.stringify to the byte; persisted state frozen with the wire; no new wire behaviour before Node is deleted

fabric-coordinator INFO 01a11e5d-16d4-727b-9ee7-2e106edc740e (2026-10-09), ADR-040 Wave 8 as revised on #131 (9ce3d507, unmerged at the time):
- My signer's serialiser must emit Node's JSON.stringify bytes exactly: non-ASCII unescaped (ensure_ascii=False), 5 not 5.0,
  no spaces (separators=(",", ":")) — json.dumps does none of that by default. Needs its own cases (floats, -0, big ints,
  lone surrogates, key order as inserted).
- Persisted state is frozen with the wire: action ledger (replay floor), pool.json and its claims, pressure ring, tools report,
  restart marker. Parity fixtures hold them, with non-ASCII strings and numbers among the arguments.
- The fabric op names its implementation (node/python) — python-dev-03's, with the cutover.
- New wire behaviour waits until Node is deleted (Node agents refuse unknown ops and arguments).
- No new Node module, ever (rule 8, ADR-001 rule 12).
Related: [[wave-8-sessions-unreadable-contract]].

*References: wave-8-sessions-unreadable-contract*

*Observed 2026-10-09 (python-dev)*
