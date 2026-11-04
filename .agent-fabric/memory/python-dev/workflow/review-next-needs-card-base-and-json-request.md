---
role: "python-dev"
class: workflow
topic: "review-next-needs-card-base-and-json-request"
description: "fabric-review next on a range starting at origin/main needs card_base; its output is a req-*.json to brief, not the .yaml"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e094d151eb298182
---

## fabric-review next on a range starting at origin/main needs card_base; its output is a req-*.json to brief, not the .yaml

`fabric-review next REQ --report R --head X` refuses a request whose range base is `origin/main` ("not a commit id"): add `card_base: <round 1's base_sha>` to the request first. It then writes `req-<round>.json` beside the request (stdout stays empty); render that with `fabric-review brief`, never the redirected stdout. A re-review that spans files the first request did not list (here policies/ and a schema the coordinator pushed onto the branch) needs `scope` and `lenses` widened in that JSON before rendering. `fabric-pr post-review` needs the report verbatim with its dispatch block, and must run from the project's working copy (from elsewhere it cannot resolve the repository). j51, PR 305, 2026-10-19.

**Why:** three rounds on #305 each hit one of these.
**How to apply:** write card_base into the first request; keep each round's report in the scratchpad as the next round's `--report`.

*Anchors: `tools/fabric/review_rounds.py::card_base`*

*Observed 2026-10-19 (python-dev)*
