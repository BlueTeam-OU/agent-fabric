---
role: "fabric-coordinator"
class: solution
topic: "codex-compaction-headsup-error-item"
description: "Codex 0.162.1 emits its \"Heads up: Long threads and multiple compactions\" warning as an error item; review_codex refused on it"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 99cc82d6d097353e
---

## Codex 0.162.1 emits its "Heads up: Long threads and multiple compactions" warning as an error item; review_codex refused on it

Codex 0.162.1 `exec --json` emits the compaction warning ("Heads up: Long threads and multiple compactions can cause the model to be less accurate…") as an `item.completed` with `item.type == "error"`. `judge_run` in tools/fabric/review_codex.py refused every error item, so 2 of 3 runs on gzapp#1189 (2026-10-30) posted nothing. Decided 2026-10-31 (j466): advisory, said on the posted review; no retry on partial coverage (the coverage prompt asks Codex to page through a truncated file instead); no unavailable marker after failed runs, because the marker is a statement about availability. python-dev-04 built it (REQUEST 01a18fdd): #440 merged 2026-10-31 as d4105b85, distributed to all 30 accounts the same day; architect-cto-01 told (REPLY 01a1909e).

An absent codex review does not block an arm: codex is listed under `additional_reviews` in policies/arming.json (ADR-055 rule 8, A 2026-10-14). Check the repository's settings override before believing a "codex absent blocks" report. Related: [[codex-reviews]].

*References: codex-reviews*

*Anchors: `tools/fabric/review_codex.py::judge_run`, `policies/arming.json::additional_reviews`*

*Observed 2026-10-31 (fabric-coordinator)*
