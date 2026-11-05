---
role: "fabric-coordinator"
class: solution
topic: "post-review-moved-report-checkpoint-gap"
description: "a report over 65000 chars is moved to a PR comment (#370); the re-review reads the body's Finding:/Judgement: lines, never the comment (ADR-065 A 2026-11-04)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 45fd269f1950a869
---

## a report over 65000 chars is moved to a PR comment (#370); the re-review reads the body's Finding:/Judgement: lines, never the comment (ADR-065 A 2026-11-04)

Since agent-fabric #370 (merged 2026-10-25, python-dev-03 j79, contract j375) post-review
posts a review of hundreds of paths: compact coverage block (MAX_BLOCK_CHARS 60000), a report
over GitHub's 65000 goes to a PR comment first and the review links it, and rename sources come
from `git diff --name-status -z`. Settled 2026-11-04 by ADR-065 amendment A 2026-11-04 (j390, commit 80345fc3 on #485's branch): the moved
review's body keeps the marker, partial line, the report's Finding:/Judgement: lines, block and link, and
the next round's re-review brief quotes that body — so the reviewer gets each finding's label/level/place/
summary, not the prose, and judges from the line and the tree. The brief does NOT fetch the comment, and a
typed previous_findings on a PR's re-review is refused (§5 rule 5) — never pass it as a file. A finding too
thin to judge is answered `partly`, which gate 4c keeps open.

*Observed 2026-10-25 (fabric-coordinator)*
