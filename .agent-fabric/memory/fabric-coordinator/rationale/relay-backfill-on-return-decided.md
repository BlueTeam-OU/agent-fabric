---
role: "fabric-coordinator"
class: rationale
topic: "relay-backfill-on-return-decided"
description: "Owner 2026-11-12: a message the InterWeave carrier alone delivered during a relay outage is re-posted to the relay on its return (j798); a data-plane cutover blocker until built"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ea7fc67f22416a0c
---

## Owner 2026-11-12: a message the InterWeave carrier alone delivered during a relay outage is re-posted to the relay on its return (j798); a data-plane cutover blocker until built

The relay-outage drill on 2026-11-12 (10:13:30Z to 10:43:51Z) showed that nothing puts a carrier-only message on the relay afterwards. `send.py` exits 3 and leaves the journal row pending. Only a hand resend of the same file writes it to the relay's record. Readers that read only the relay (`fabric-pr arm` AUTHORIZES, `gzcoord-inbox --replay`, `fabric-history`) miss it. devex-tooling found this (OBSERVATION 01a1cf5d-a4b3).

The owner chose backfill on return over having those readers read the InterWeave copies. It is contracted to python-dev-03 as their j134 (REQUEST 01a1cf63-19d2). Its shape:
- it runs without a session, from agentd;
- the source is the sender's journal row, posted verbatim;
- it checks that the relay does not already hold the message, so there is never a second copy;
- it keeps order and has an age bound;
- it logs each backfill for the parity report.

**Built 2026-11-13:** #573 (tools/fabric/gzcoord/backfill.py, agentd ticks it every minute) writes gzcoord-backfill.jsonl {mid, outcome, at, delay_s, channel}, but nothing collects or reports it: carrier_evidence.py has no section for it, and parity.py does not read it. A reader is contracted to python-dev-02 (REQUEST 01a1d548): a fifth evidence section, `backfills`, and a fourth relay-drill property that older collections show as "not judged". The ADR-064 rule 11 and ADR-029 §2 amendments are mine, as commits onto their branch. Lesson: a log written "for the report" is not evidence until the collector and the report read it. Check its reader before calling it done. See [[data-and-reader-together]].

**How to apply:** this blocks the data-plane cutover (ADR-064 rule 11). Record it in the ADR-064 amendment that comes with the cutover. My own drill notice wrongly promised the backfill and had to be corrected by broadcast (01a1cf5e): check what send does before promising behaviour. Related: [[operator-engine-pin-decided]].

*References: data-and-reader-together, operator-engine-pin-decided*

*Observed 2026-11-13 (fabric-coordinator)*
