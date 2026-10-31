---
role: "fabric-coordinator"
class: workflow
topic: "inbox-wait-not-monitor"
description: "Watch the GZCoord inbox with a background `gzcoord-inbox --until-delivery` (no loop; one watch per login) that exits on a delivery, not a 30-minute Monitor: every Monitor expiry woke the session and rang the deck's job-end sound (the…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 021e202a016e0fb7
  - fb83ff2a555d3ca7
---

## Watch the GZCoord inbox with a background `gzcoord-inbox --until-delivery` (no loop; one watch per login) that exits on a delivery, not a 30-minute Monitor: every Monitor expiry woke the session and rang the deck's job-end sound (the owner, 2026-10-10)

The owner, 2026-10-10: "now that we have sound and green bullet when a job ends, having
the inbox restart notification have become an annoying thing .... can we do it in a non
recurring way?" The Monitor on `gzcoord-inbox --follow` expires every 30 minutes and each
expiry plus re-arm was a wake, a turn and a sound, message or not.

**Why:** Fleet Deck turns every end of turn into a sound and a bullet; a wake must mean
something happened.

**How to apply:** run in the background (Bash `run_in_background`, timeout 7200000) a loop
of `gzcoord-inbox --wait 1800` that prints and exits only when the output carries a
message (`for you` / `[GZCOORD/1]`) or the command fails; after handling the delivery,
start it again. A quiet session is woken about once per 1 h 55 min, by the watch's own `--deadline` (exit 0 with "quiet for <N> min, nothing delivered; run the watch again"), before the harness's 2-hour cap (#285, 2026-10-16).
The script lives in the session scratchpad (`inbox-wait.sh`); rewrite it in a new
session.

Updated 2026-10-14: the command is `gzcoord-inbox --until-delivery`, run in the background with the longest timeout (7200000 ms); it exits on the first delivery addressed here and is restarted after reading it. The watch-on-stop hook requires one before a turn ends. Never a Monitor, never a second watch.

*Observed 2026-10-16 (fabric-coordinator)*
