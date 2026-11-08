---
role: "python-dev"
class: solution
topic: "carrier-read-on-relay-failure-j115"
description: "j115 #499 — wait_loop reads the carrier when the relay fetch fails; relayError key; follow-mode test traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - cf61d3cbc637629d
---

## j115 #499 — wait_loop reads the carrier when the relay fetch fails; relayError key; follow-mode test traps

#499: `watch.py wait_loop` re-raised a failed relay fetch before `iw.unseen()`, so a carrier-only message never showed in an outage. Now (ledger and iw present) the error stands for an empty page, the carrier is decided through the unchanged ledger lock, and the error is raised only if nothing was delivered; a delivered result carries `relayError`, which inbox.py must still report (drain: stderr line + `explain_relay_error` code; watch: after show_page; `down` is not cleared by it).
**Why:** a review (F1) found the first version swallowed the relay's line and a refused token's exit 4 whenever the carrier delivered. **How to apply:** any new consumer of a wait_loop result reads `relayError`. Tests: tests/test_gzcoord_carrier_inbox.py `World.relay_down`/`watch()`; the `--follow` case needs the carrier record to arrive after a failed arm (down only set then; retry is 30 s), and a mutation of the `down` guard is the only proof it guards. Arm count rule here was "1 or more" (dry-run), no owner word needed. `fabric-review next --pr N --head SHA` (not --report) for a re-review; request range must be commit ids.

*Observed 2026-11-07 (python-dev)*
