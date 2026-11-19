---
role: "fabric-coordinator"
class: rationale
topic: "torn-line-reshow-not-semantics"
description: "why SEMANTICS.md gets no \"may repeat\" re-show wording after #576 (torn shown-ledger line)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ce6872cf2ffadef2
---

## why SEMANTICS.md gets no "may repeat" re-show wording after #576 (torn shown-ledger line)

2026-11-13, j806: #576 (python-dev-02 j143, merged 6c5dc6f0) proved a torn
`gzcoord-shown.jsonl` final line re-shows the message once flagged "may
repeat"; never lost, never twice unflagged. It asked the protocol owner
whether SEMANTICS.md should say so. Decided no: SPEC §7.2 already makes
delivery at-least-once with duplicates by design, discarded by
MESSAGE-ID; the flag is the reference inbox's presentation (implementation),
and the tears were constructed, never observed live — the charter's bar
for a protocol change is a pattern seen across sessions. Reopen only if a
live re-show causes a duplicate action between two sessions.
Related: [[gzcoord-messaging]]

*References: gzcoord-messaging*

*Observed 2026-11-13 (fabric-coordinator)*
