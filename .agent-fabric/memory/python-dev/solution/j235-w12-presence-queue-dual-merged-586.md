---
role: "python-dev"
class: solution
topic: "j235-w12-presence-queue-dual-merged-586"
description: "W12 merged (#586): Leg over the agentd socket for presence/queue on dual; Down classification, review traps, verbatim-report cost"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 584195137564b909
---

## W12 merged (#586): Leg over the agentd socket for presence/queue on dual; Down classification, review traps, verbatim-report cost

#586 (2026-11-13, head 57235d9e): `control_link.Leg` (Session wrapper) lets `presence.ask_presence` and `queue.ask_holder` ride the account's own agentd socket when `cfg["control_carrier"] == "dual"`; the relay post stays first. `control_link.Down` carries both failures and keeps the relay's status/connection_refused/sent; a handed socket clears them (unknown). Self-asks and accounts with no socket fall back to the relay.

**Why:** a relay outage had stopped addressed sends (D1, owner 2026-11-13). Review found, and the fixes carry: an agentd `refused` event sent nothing (SessionRefused, not handed); an all-targets failure is "handed" unless the why starts with a definite non-send prefix (`_NEVER_SENT`, wording-dependent); "the operator's agentd" wording is fabric-ctl's, re-worded in Leg; suites that spawn presence.py/queue.py with an inherited env dial the live socket under the committed `dual` (pin `FABRIC_CONTROL_CARRIER=relay`, listed in test_run_control_carrier).

**How to apply:** carried P3 F6: with the relay down an ordinary timeout says "connection closed before the answers" because Server closes at its own `end`; fix = an `end` event or a deadline margin. send.py drops presence.py's stderr when an answer parses (send.py lane). The re-review brief and the review report must be passed VERBATIM (a condensed report file is not a post; I wrote one and deleted it); the brief is ~46 KB. Three timing suites (message_transport, post_review_shape_guard, project_import) failed under a full-suite load and passed alone; the owner accepted the reruns. See [[post-review-needs-a-file-the-owner-can-run]] [[suites-inherit-launch-stamps]].

*References: post-review-needs-a-file-the-owner-can-run, suites-inherit-launch-stamps*

*Anchors: `tools/fabric/gzcoord/carrier/control_link.py::class Leg`, `tools/fabric/gzcoord/carrier/control_link.py::class Down`, `tools/fabric/control/presence.py::open_leg`, `tools/fabric/control/queue.py::open_leg`, `tests/test_run_control_carrier.py::EverySuiteThatRunsPresenceOrQueuePinsItself`*

*Observed 2026-11-13 (python-dev)*
