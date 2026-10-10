---
role: "fabric-coordinator"
class: threads
topic: "drain-report-last-run-wins"
description: "FIXED (135b02b, ed5ca52): the drain report gathers every bundle of one drain and keeps each harvest; was — per-bundle runs overwrote last-drain-report.json"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - 706c2df1196b7349
  - bfbf0c727ce475c7
---

## FIXED (135b02b, ed5ca52): the drain report gathers every bundle of one drain and keeps each harvest; was — per-bundle runs overwrote last-drain-report.json

FIXED by 135b02b and ed5ca52 (on main by 2026-09-27); this note stayed OPEN after the fix — see [[assemble-subheading-breaks-idempotence]].

OPEN (found 2026-09-25). A drain across accounts is one
`assemble.py --bundle` per account into the same working copy, and each
run rewrites `.agent-fabric/memory/last-drain-report.json` whole. The
committed report describes only the last bundle. `collision_decisions`
applied by earlier runs are gone, which contradicts memory/README.md's
statement that "every applied decision is recorded". An index-only
refresh (empty claims for a role, which is how gzapp.decks and gzapi.brand
re-list brand-comms' domain slice) writes `"watermarks": {}`.

The workaround used that day: end each project with a real bundle run
so the watermark is real, restore the report in index-only repositories
(`git checkout -- last-drain-report.json`), and list the owner's
decisions in the commit and PR text. The fix belongs on the next branch.
Either merge into the existing report (watermark max per host, decisions
appended, per-role telemetry keyed by agent), or accept several bundles
in one run. Add an index-only mode that leaves the report alone. See
[[assemble-subheading-breaks-idempotence]].

*References: assemble-subheading-breaks-idempotence*

*Observed 2026-09-25 (fabric-coordinator)*
