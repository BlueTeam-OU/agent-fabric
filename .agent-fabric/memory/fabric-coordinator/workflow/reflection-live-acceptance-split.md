---
role: "fabric-coordinator"
class: workflow
topic: "reflection-live-acceptance-split"
description: "A REQUEST whose acceptance needs a live run (fabric-ctl on all, a deck cutover, a host measurement) splits ACCEPTANCE into what the builder delivers and the one line I or the owner run and paste back; the builder's session usually cannot…"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9e5b831f9776b576
---

## A REQUEST whose acceptance needs a live run (fabric-ctl on all, a deck cutover, a host measurement) splits ACCEPTANCE into what the builder delivers and the one line I or the owner run and paste back; the builder's session usually cannot run it

Three builders that week reached the live step of my acceptance and stopped. One was not a host operator, so `fabric-ctl all …` was refused. One needed the owner to restart the deck to get the after-numbers. One was refused a read of the deck's process stats by auto mode. Each time the work went quiet until I noticed and ran the step myself, or handed it to the owner.

**Why:** the fences that bar a contributor from fleet ops and the owner's terminal are deliberate. My acceptance was written as if the builder could cross them.
**How to apply:** in a REQUEST, write ACCEPTANCE in two parts. "You deliver" lists what the builder can check in its own session. "I run" names the exact live command, who runs it (me, or the owner via `! <script>`), and where the result is recorded (`docs/live-checks/`). Add the "I run" step to my own job as a blocker, so it is not left to whoever notices. Related: [[owner-commands-one-line]], [[fabric-ctl-assist-owner-terminal]].

*References: fabric-ctl-assist-owner-terminal, owner-commands-one-line*

*Observed 2026-11-01 (fabric-coordinator)*
