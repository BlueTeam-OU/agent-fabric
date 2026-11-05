---
role: "fabric-coordinator"
class: workflow
topic: "scratch-fabric-worktree-misses-sibling-hygiene"
description: "assembling a drain from a scratch agent-fabric worktree skips other projects' hygiene bans (e.g. gzapp's city name) unless their working copies sit beside it"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b005594660c7bd23
---

## assembling a drain from a scratch agent-fabric worktree skips other projects' hygiene bans (e.g. gzapp's city name) unless their working copies sit beside it

`assemble.py` loads every project's hygiene list from the working copies it finds *beside* the fabric root (`workingcopy.sibling_working_copies`), plus the one `--working-copy`. A fabric worktree in a scratchpad has no siblings, so gzapp's `\bkutaisi\b` ban was silently not applied: in j505 (2026-11-03, [redacted]-shop-transit #5) the first run left the city name unredacted and differed from the fabric half's control (`~/drain/2026-10-31/fixed/wt/[redacted]-shop-transit`), while main's corpus already carried `[redacted]`.

**Why:** the ban list is every project's, not the target's; a missing sibling is no error, just a missing list.
**How to apply:** put the scratch fabric worktree in its own directory beside an origin worktree of each project that has `.agent-fabric/hygiene.json` (today only gzapp), e.g. `ws/agent-fabric` + `ws/gzapp`; then `diff -r` against the control. See [[drain-project-half-after-fabric-half]].

*References: drain-project-half-after-fabric-half*

*Anchors: `agent-fabric:tools/fabric/assembler/intake.py::sibling_working_copies`*

*Observed 2026-11-03 (fabric-coordinator)*
