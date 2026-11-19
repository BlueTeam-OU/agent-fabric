---
role: "fabric-coordinator"
class: rationale
topic: "interweave-only-cutover-owner-decisions"
description: "owner 2026-11-13: GZCoord data plane to InterWeave only — D1 data plane first then relay retired, D2/D10 three rungs by signed action, D4 grants from a verified journal row, D5 give up seq/alerts/channel record"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - beb4f2b583c37c88
---

## owner 2026-11-13: GZCoord data plane to InterWeave only — D1 data plane first then relay retired, D2/D10 three rungs by signed action, D4 grants from a verified journal row, D5 give up seq/alerts/channel record

The owner asked on 2026-11-13 what still stands between the fleet and a GZCoord data plane on InterWeave only, and asked for the work to be dispatched. The plan is docs/proposals/gzcoord-interweave-only-cutover.md. It is commit 77f368b9 on the local branch develop-qzapp/user/docs/gzcoord-interweave-only-cutover, not pushed yet; job j814 opens its PR. The owner's answers, the same day, in the coordinator's session (AskUserQuestion), all as the plan recommended:

- D1: the data plane first, gates 1 and 2. W12 sits inside gate 2: presence and the queue move off the relay's outage path. Retiring the relay, the control plane included, is a later gate 3.
- D2 and D10: three rungs, relay-record, then carrier-record, then carrier-only. A signed action moves each account and its state keeps the mode; nothing is committed in a file. python-dev-02 and python-dev-03 go first, the coordinator last.
- D4: `fabric-pr arm` may read AUTHORIZES and WAIVES from the arming login's own journal, but only for a row addressed to that login whose sender the carrier verified. This needs an amendment of ADR-041 rule 7.
- D5: give up the global seq, keyword alerts on others' traffic and the whole-channel record. The relay's last database copy is kept encrypted on Proton Drive for a period the owner has not named yet.

Not asked yet: D3 (#573 merges now and goes off at carrier-only), D6 (TO-ROLE decided at arrival), D7 (journal-off), D8 (soak lengths), D9 (second host; architect-cto's question on one-way dialling).

**Why:** the owner wants no relay in the data path. The plan showed that the switch needs a mode, journal-first readers and presence off the relay, not only a flag.
**How to apply:** amend a record now only for what was decided, never for a gate not yet given. The plan's §4 lands ADR-033, ADR-064 rules 7, 8, 11 and 14, and ADR-041 rule 10 at each gate's word. On 2026-11-14 the owner's answers went in as ADR-041 rule 7 (D4, so W4 can be built) and ADR-064 §7 (D1, D2, D5, D10), on #604 with the plan. Dispatched: W3 to python-dev-01 (j233) and W10 to python-dev-04. W1 is j811, W2 is mine. Related: [[relay-backfill-on-return-decided]].

**2026-11-14:** #604 merged (e112b2c4, armed on the owner's word "arm 604", boundary change under 8) and was distributed to all 30 accounts. It holds the plan read against main, W4 (devex-tooling) folded, ADR-041 rule 7, ADR-064 §7 and ADR-029 §2 `interweave-mode`. Done: W3, W4, W5, W10, W12, W14. Left: W1's read-back, W2 (mine: drills and parity report), W6 to W9, W11, W13, then the gates. ADR-041 rule 7's relay-row half and the FROM condition are mine, not the owner's (history note).

*References: relay-backfill-on-return-decided*

*Observed 2026-11-13 (fabric-coordinator)*
