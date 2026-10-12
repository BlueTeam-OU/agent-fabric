---
role: "fabric-coordinator"
class: workflow
topic: "inbox-wait-not-monitor"
description: "Watch the GZCoord inbox with a background `gzcoord-inbox --wait` loop that exits on a delivery, not a 30-minute Monitor: every Monitor expiry woke the session and rang the deck's job-end sound (the owner, 2026-10-10)"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-12"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fb83ff2a555d3ca7
---

## Watch the GZCoord inbox with a background `gzcoord-inbox --wait` loop that exits on a delivery, not a 30-minute Monitor: every Monitor expiry woke the session and rang the deck's job-end sound (the owner, 2026-10-10)

The owner, 2026-10-10: "now that we have sound and green bullet when a job ends, having
the inbox restart notification have become an annoying thing .... can we do it in a non
recurring way?" The Monitor on `gzcoord-inbox --follow` expires every 30 minutes and each
expiry plus re-arm was a wake, a turn and a sound, message or not.

**Why:** Fleet Deck turns every end of turn into a sound and a bullet; a wake must mean
something happened.

**How to apply:** run in the background (Bash `run_in_background`, timeout 7200000) a loop
of `gzcoord-inbox --wait 1800` that prints and exits only when the output carries a
message (`for you` / `[GZCOORD/1]`) or the command fails; after handling the delivery,
start it again. A quiet session is woken at most once in two hours (the harness's cap).
The script lives in the session scratchpad (`inbox-wait.sh`); rewrite it in a new
session.

*Observed 2026-10-10 (fabric-coordinator)*
