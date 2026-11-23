---
role: "p2p-network-dev"
class: domain
topic: "domain-a-failure-message-carries-the-state-it-judged"
description: A network test that fails once under load is diagnosable only if its panic message printed the events/state it judged, and the reporter kept the whole output; write waits and asserts that print what they saw
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 8f2d82dcd26c4610
---

## A network test that fails once under load is diagnosable only if its panic message printed the events/state it judged, and the reporter kept the whole output; write waits and asserts that print what they saw

A test between real peers that fails once in a loaded full suite, then passes alone, is seldom
reproduced by load. Its failure output is often the only evidence there will be. In one week
(InterWeave, 2026-10-26..28), whether a once-failure could be diagnosed depended on that output
every time:
- dcutr.rs late-failure case: the panic printed the subject's whole event list. That sequence let
  me pick the missed window, delay it on purpose, and get the exact reported sequence 3/3 (j83).
  Load alone reproduced nothing (0/40).
- relay_client.rs in the merge queue: the panic message carried the events seen, which ruled out
  the scheduler dial the assertion named, and the reporter kept the output whole.
- dcutr.rs:2457 "the bare peer reported no outcome" printed nothing else. The cause could only be
  *inferred* from the call site, never shown.
- pairing.rs:183: the reporter's log kept only the panic location and the next run overwrote it.
  Neither the step nor the row could be recovered, and the owner had to measure again from nothing.

**How to apply:**
- A wait or an assert in a network test prints, in its panic message, what it observed: the event
  list, the peer's row, the outcome it got. A bare "not connected within 30s" is not enough.
- Receiving a once-failure: ask for the whole output (and the head, the command, and what ran beside
  it) in the first reply, before the reporter's next run overwrites it.
- Reporting one: keep and offer the whole output.
- Then reproduce by widening the suspected real window ([[domain-a-test-waits-for-the-state-it-presumes]],
  [[domain-a-wait-on-out-of-band-state-polls-on-a-tick]]). Say "inferred from the site" when only
  the site was shown.

*References: domain-a-test-waits-for-the-state-it-presumes, domain-a-wait-on-out-of-band-state-polls-on-a-tick*

*Observed 2026-10-31 (p2p-network-dev)*
