---
role: "p2p-network-dev"
class: domain
topic: "domain-a-two-party-case-ends-on-an-explicit-close"
description: "In a two-party end-to-end case, the side that returns first and stops its runtime can lose the acceptance of its last answer (outcome unknown on a closing connection is within contract); the side that needs the last confirmation sends an…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 6a3708d08cc49bf0
  - 82d500127a32f8bf
---

## In a two-party end-to-end case, the side that returns first and stops its runtime can lose the acceptance of its last answer (outcome unknown on a closing connection is within contract); the side that needs the last confirmation sends an explicit close, and the other returns only on it

InterWeave's relayed `paths` device case failed once in a few runs on a Pixel. The phone's half read the
desktop's answer, returned pass, and the app's runner stopped the service 0.48 s later. The acceptance of
that answer was lost on the closing connection, so the desktop half waited for a confirmation it could never
get. TRANSPORT.md's "Outcome unknown" allows exactly this (PeerUnreachable after a written request means "not
confirmed"), so the transport kept its contract and the race was in the test's design. `human_chat` had the
same shape: the desktop required its replies' acceptance only after the phone's case had stopped.

The fix in both: the side that needs the last confirmation waits for it while the other side is still
running, then sends an explicit close (`close_exchange`, or a closing chat message where the phone reads
through the app's facade). The other side returns only when it sees the close. Its proof needs both halves
built at or after the fix. A new host side against an old APK keeps the old race, because the old phone half
ignores the close.

**How to apply:** for every two-party case, find the last message whose delivery is asserted, and make sure
the party that would observe its loss is the one that ends the exchange. A pass that leans on the other side
"probably still being up" is timing luck. Related: [[domain-a-test-waits-for-the-state-it-presumes]],
[[domain-device-tests-run-in-the-app-process]].

The same rule holds for a mere OBSERVATION, not only an acceptance (2026-10-24, two phones, row 1 of plan
§29 (e)): a far-end case that returned on seeing the dialler's connection ended its process, so its runtime,
and the connection closed 49 ms after it came up, before the dialler's case read its own peer row (polled
every 250 ms); the dialler's redial then failed into backoff. Host stand-ins cannot show it, since their
runtime outlives the case. Fixed in de47200d: the far end returns only once the dialler has left, and the
host ends the dialler after its case passes. It held in BOTH directions the same day: after that fix,
the dialler's case returned on seeing the connection and stopped its runtime 51 ms later, so the far end
missed it; fixed in 96c2a52b by holding the connection 5 s (also asserting it stays up). Any case whose
return the other side's evidence depends on must outlast that evidence -- check every half of a two-device
row for this before the first device build, since each miss costs a rebuild and a reinstall.

Third instance, the same day: a two-phone `pair` step whose first side REQUIRED its close's acceptance failed
1 run in 3 with PeerUnreachable, because the second side ends on reading the close and its runtime with it --
the very race `close_exchange` already documented as "outcome unknown, reported, not relied on". The close is
only a signal; the second side's pass proves it arrived. And the side that sends the close should itself end
only once the other has left (its row disconnected), so the other is never owed an acceptance by a runtime
that is gone (cc64aa55).

*References: domain-a-test-waits-for-the-state-it-presumes, domain-device-tests-run-in-the-app-process*

*Observed 2026-10-24 (p2p-network-dev)*
