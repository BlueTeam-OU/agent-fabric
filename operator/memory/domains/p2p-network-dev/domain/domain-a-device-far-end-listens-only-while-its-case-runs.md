---
role: "p2p-network-dev"
class: domain
topic: "domain-a-device-far-end-listens-only-while-its-case-runs"
description: "on a phone each instrumented case is its own process, so a \"stays unconnected\" control with no far-end case running measures nothing"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 8b45ccadf3f8c66f
---

## on a phone each instrumented case is its own process, so a "stays unconnected" control with no far-end case running measures nothing

On Android each `am instrument` case is its own app process, and the embedded runtime (and its listener) lives only while that case runs. A negative control of the shape "A stays unconnected to B for N s" passes vacuously if no B case is running during the window: nothing is listening to be dialled. Host stand-ins hide this, because their runtime outlives each case. Found by the blind review of #421 (F1): rows 4, 8 and 12 of the cache-on run file were not a control. Fixed at bf114692 with `await_peer`'s `apart` window, gated by `until_listening`, plus an assertion that B's case was still running when A's window ended.

**Why:** a control that cannot fail is the most dangerous kind of passing test, and stand-in runs cannot show it.

**How to apply:** for every device-run negative assertion, check that the far end is up and listening for the whole window. Gate on a socket check, not on timing, and assert that the far end outlived the window.

Related: [[domain-device-tests-run-in-the-app-process]], [[domain-a-test-waits-for-the-state-it-presumes]].

*References: domain-a-test-waits-for-the-state-it-presumes, domain-device-tests-run-in-the-app-process*

*Observed 2026-10-24 (p2p-network-dev)*
