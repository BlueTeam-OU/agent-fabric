---
role: "p2p-network-dev"
class: domain
topic: "domain-a-two-party-case-ends-on-an-explicit-close"
description: "In a two-party end-to-end case, the side that returns first and stops its runtime can lose the acceptance of its last answer (outcome unknown on a closing connection is within contract); the side that needs the last confirmation sends an…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
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

*References: domain-a-test-waits-for-the-state-it-presumes, domain-device-tests-run-in-the-app-process*

*Observed 2026-10-22 (p2p-network-dev)*
