---
role: "p2p-network-dev"
class: workflow
topic: "a-flake-is-diagnosed-from-one-recurrence"
description: "A once-failing networking test is diagnosed from one recurrence only if its assertion prints the subject's state row or event list and the whole run output is kept; reproduce contention with several test binaries at once, not more threads…"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - cc7557829663c968
---

## A once-failing networking test is diagnosed from one recurrence only if its assertion prints the subject's state row or event list and the whole run output is kept; reproduce contention with several test binaries at once, not more threads in one

Twice in one week a flake reported as a panic line was unreadable,
and the cause came from the full text the next time:
- the cache-alone pairing case: the first report kept only the panic
  header (the log was filtered, then overwritten); the recurrence kept
  the gate row and the log, which named `no_known_address` and no
  dial, and that gave the cause in minutes;
- a relay_client case evicted from the merge queue: the job log's full
  event list showed `Unexpected peer ID` then AddressQuarantined,
  which the four-event summary in the report did not.

**How to apply:**
- An assertion in a timing-dependent test prints the subject's state
  for the thing waited on (gate row, event list, the log once, labelled
  per peer), so a recurrence is self-diagnosing.
- Asking a reporter: name the exact fields wanted, and ask them to keep
  the whole output next time; for CI, read the job log, not the summary.
- Reproduce under contention by running several test binaries at once
  (1 in 24 here), since one binary at more threads did not reproduce
  in 25 runs. Compare with [[dialer-established-precedes-listener-auth]]
  on not adding driving that changes the race.

*References: dialer-established-precedes-listener-auth*

*Observed 2026-10-31 (p2p-network-dev)*
