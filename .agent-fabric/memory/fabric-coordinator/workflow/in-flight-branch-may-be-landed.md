---
role: "fabric-coordinator"
class: workflow
topic: "in-flight-branch-may-be-landed"
description: "fabric-pr gate --in-flight lists a for/ branch whose content already landed under another commit; check main's content before reading it as live work"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 89aadc005a2da9c9
---

## fabric-pr gate --in-flight lists a for/ branch whose content already landed under another commit; check main's content before reading it as live work

`fabric-pr gate --in-flight --path runtime/claude-code/hooks/watch-on-stop.py`
(2026-11-09, j638) listed python-dev-02's
`for/user/j626-stop-hook-spares-relay-down` (8b363ea6, ahead=1) as in
flight, yet #506 had merged that hook change on 2026-11-08 as other
commits: `git grep relay_down origin/main -- <path>` found it. "Not an
ancestor" is not "not landed" (see [[ancestor-is-not-landed-check-reverts]]).

**Why:** the holder-choice rule (gzcoord-send §2) picks the login whose
pushed branch touches the path; a stale branch still makes that login
the natural holder (it knows the code), but it is not work in progress.
**How to apply:** before citing an in-flight branch as live, grep main
for its content; in the REQUEST, tell the holder the stale branch can go.

*References: ancestor-is-not-landed-check-reverts*

*Observed 2026-11-09 (fabric-coordinator)*
