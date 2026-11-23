---
role: "p2p-network-dev"
class: domain
topic: "domain-a-new-refusal-gets-a-down-level-answer"
description: "Adding a refusal reason to an existing write at protocol minor N: what a connection that negotiated below N is answered, so the rule still holds for old clients and their decoders read it right"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 936b12e2c64c0b1d
---

## Adding a refusal reason to an existing write at protocol minor N: what a connection that negotiated below N is answered, so the rule still holds for old clients and their decoders read it right

A new refusal must still hold for a client below the minor that names it. That client's write is often the very
case the rule exists for, and its decoder refuses a name it does not know. So the server answers it with an
EXISTING code whose documented meaning has the same effect for that client. Never pick a success, a code that
names a rule the input passed, or "outcome unknown" when the outcome is known.

Two rulings on InterWeave LOCAL-IPC by architect-cto (2026-10-23):
- `own_peer` (2.9) is answered `grammar` below 2.9. It is still a refusal by name that an old client shows.
- `superseded` (2.10) is answered the error `Internal` below 2.10. LOCAL-IPC already says `Internal` means
  "nothing changed", so every older client re-reads. `ok`/`unchanged` would say the write stood. `grammar` names
  a rule the address passed. `CancellationRaced` says unknown when the outcome is known.

**How to apply:** for each method that gains the reason, list the existing answers that an old client reads as
"not applied". Pick the one whose effect matches, and write it in the contract as "a downgrade by version, not
the rule". Test the gate (the minor check) with a mutation, as 0c0c40e8 did.
Related: [[domain-a-staleness-refusal-is-checked-last]].

*References: domain-a-staleness-refusal-is-checked-last*

*Observed 2026-10-25 (p2p-network-dev)*
