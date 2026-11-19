---
role: "fabric-coordinator"
class: workflow
topic: "j585-gzapp-lint-rides-drain"
description: "gzapp CI memory-lint line count: what a drain clears and what it does not; count only gzapp:-prefixed lines"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - cdb05dc016409c12
---

## gzapp CI memory-lint line count: what a drain clears and what it does not; count only gzapp:-prefixed lines

gzapp's ban-checks CI step runs `lint.py --working-copy gzapp=$GITHUB_WORKSPACE`, and its log
prints agent-fabric's own corpus warnings too (142 lines on 2026-11-09), so a "N lint lines"
report from that log mixes two repositories: count `warning: gzapp:` lines only.

j585 (closed 2026-11-09): before drain gzapi-org/gzapp#1231 gzapp had 9 INDEX drift lines, 112
stale-hard, 53 maybe-stale, 116 dead-link; after it, measured locally (gzapp 7af66bf0e, fabric
426ab783) and identical in CI run 42553330078: 0 INDEX drift, 109 stale-hard, 46 maybe-stale,
126 dead-link. A drain's index-only run clears INDEX drift (the only failing kind); staleness
warnings need correction memories at source, not a drain. Dead links rose: 73 of 179 links are
[[ADR-NNN]], which the lint does not resolve — job j680 decides that. [[drain-procedures]]

*References: ADR-NNN, drain-procedures*

*Observed 2026-11-09 (fabric-coordinator)*
