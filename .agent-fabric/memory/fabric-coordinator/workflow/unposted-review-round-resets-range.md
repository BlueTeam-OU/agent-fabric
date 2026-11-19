---
role: "fabric-coordinator"
class: workflow
topic: "unposted-review-round-resets-range"
description: "A review report that was written but never posted with fabric-pr post-review does not count; the next re-review's range starts at the last POSTED head, and its findings are not \"previous findings\""
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: gzapp.decks
    working_copy: gzapp.decks
derived_from:
  - 83f56e5d8669f964
---

## A review report that was written but never posted with fabric-pr post-review does not count; the next re-review's range starts at the last POSTED head, and its findings are not "previous findings"

On gzapp.decks #29 (job j660, 2026-11-09), round 4 reviewed e4333eb..03f2bb3 and raised F14 and F15. The report was saved locally but never posted. The fixes e52616f and b22f32c carried `Answers: F14` / `Answers: F15` trailers. The next `fabric-review brief` refused range 03f2bb3..b22f32c: a re-review starts at the last posted review's head (4e0a809). The rendered brief also did not list F14/F15 under Previous findings, so the reviewer could not judge them by number.

**Why:** the gate and the brief renderer read reviews from the PR, not from the local state directory. A report that is not posted leaves no trace there.

**How to apply:** post each review report (`fabric-pr post-review <n> < report`) as soon as it has been judged, before you commit any fix that answers it. Before writing a re-review request, compare `gh api repos/<repo>/pulls/<n>/reviews` against the local `report-round-*.md` files. If a round is missing on the PR, the next re-review must cover everything from the last posted head.

*Anchors: `agent-fabric:tools/fabric/review_brief.py::starts at its last review`*

*Observed 2026-11-09 (fabric-coordinator)*
