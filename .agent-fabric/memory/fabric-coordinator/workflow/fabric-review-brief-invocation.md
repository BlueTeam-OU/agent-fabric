---
role: "fabric-coordinator"
class: workflow
topic: "fabric-review-brief-invocation"
description: "How to call fabric-review brief for a PR review and re-review: request file as the only argument, no render verb, no previous_findings"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6199d9793e9aa19d
---

## How to call fabric-review brief for a PR review and re-review: request file as the only argument, no render verb, no previous_findings

`fabric-review brief <request.yaml>` takes the request file as its only argument (2026-11-08, #508). Two other forms fail:
- `fabric-review brief 508` reads "508" as a file and exits 2.
- `fabric-review brief render <file>` prints the usage line, exit 2, even though the usage text names a `render` verb.

The request is flat YAML with these keys: mode, pr, job_id, repository (the worktree path), range (full shas), objective, requirements, invariants, scope, out_of_scope, lenses. For a re-review, also give review_round and card_base (the first round's base).

Leave `previous_findings` out of a PR's re-review. The renderer refuses it and reads the previous report from the last posted review.

The rendered brief can be over 7 KB. Instead of pasting it into the dispatch, put the dispatch block inline and tell the code-review agent to Read the brief file from the scratchpad. That worked for rounds 2 and 3 of #508.

Separately, when a review fix edits an ADR amendment that is still unmerged in the same PR, the commit needs an `ADR-Editorial:` trailer. Without it, adr staged-check refuses the commit.

*Anchors: `tools/fabric/review_brief.py::previous_findings`, `tools/fabric/review_brief.py::card_base`*

*Observed 2026-11-08 (fabric-coordinator)*
