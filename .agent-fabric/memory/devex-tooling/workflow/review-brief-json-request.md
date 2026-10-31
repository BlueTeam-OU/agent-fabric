---
role: "devex-tooling"
class: workflow
topic: "review-brief-json-request"
description: "fabric-review brief takes a JSON request (no render verb); card_base when the base is off main, previous_findings for a re-review, fixed lens names"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d3ddbe23b3f91423
---

## fabric-review brief takes a JSON request (no render verb); card_base when the base is off main, previous_findings for a re-review, fixed lens names

`fabric-review brief <request.json>` renders the brief; `fabric-review brief render …` prints the usage line and exits 2, even though that usage line names `render`. The YAML subset refused a `- item` whose text held `*` (seen 2026-10-13, gzapp #1116), reporting "not `key: value`". JSON, built with python's json.dumps, is accepted as is and needs no quoting care. Keys: mode, repository, range, objective, requirements[], scope[], out_of_scope[], invariants[], lenses[]. A range whose base is not on origin/main (a fold off a PR branch) needs card_base: git merge-base <base> origin/main, in full. mode re-review needs previous_findings: a path to a file holding the round's report. Lenses are only cleanup, concurrency, database, distributed-systems, general, incomplete-migration, performance, portability, protocol, security (seen 2026-10-14, j131).

*Observed 2026-10-14 (devex-tooling)*
