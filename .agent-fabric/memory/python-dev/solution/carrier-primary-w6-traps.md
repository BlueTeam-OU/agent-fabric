---
role: "python-dev"
class: solution
topic: "carrier-primary-w6-traps"
description: "j125 #613 (W6 to W8): what the review rounds found in making the carrier the transport of record; the engine must say queued 0, mirror needs a bound and token refresh, journal rows name the transport"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 70fb08bc09af8ac7
---

## j125 #613 (W6 to W8): what the review rounds found in making the carrier the transport of record; the engine must say queued 0, mirror needs a bound and token refresh, journal rows name the transport

j125, #613 merged 2026-11-14 (W6 carrier as Primary, W7 inbox half, W8 gzcoord-send). Traps found by five review rounds:

- A transport that is the record must raise where the mirror stayed silent; the same adapter serves both (`post_result(fail_open=)`, `wait` strict).
- "Proved unsent" is only an explicit `queued: 0` from the engine; the engine must say it for every refusal before the first record (`NotRecorded`), else the sender reads "outcome unknown" and a pending row never closes.
- A mirror needs its own short call bound (the relay client's is 300 s), a token refresh of its own (nothing else refreshes it when the carrier leads), and a stderr line worded by error class.
- The journal row's carrier must be named by `send.py` (`--carrier interweave`); the default is the relay's name and the relay-outage evidence counts it.
- Engine tests hold the engine `clock` still: a wait must use real time. A `wait` test with the clamp patched small must leave `stop` clear.
- Hook supply: a session may not commit in a second worktree (job guard); patch saved, queued as a job.

**Why:** each was a P2 or a P3 in review rounds, all in code that passed its first tests.
**How to apply:** before moving a primary, list every answer shape the adapter reads and every journal field a sender writes.

*Anchors: `tools/fabric/gzcoord/carrier/engine.py::NotRecorded`, `tools/fabric/gzcoord/transport/carrier.py::CarrierPrimary`, `tools/fabric/gzcoord/transport/relay.py::RelayMirror`*

*Observed 2026-11-14 (python-dev)*
