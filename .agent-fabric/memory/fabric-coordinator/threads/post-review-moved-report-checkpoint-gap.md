---
role: "fabric-coordinator"
class: threads
topic: "post-review-moved-report-checkpoint-gap"
description: "post-review moves an over-65000-char report to a PR comment (#370); a later round's checkpoint brief then quotes only the pointer"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b4cb0c7c13ee12c6
---

## post-review moves an over-65000-char report to a PR comment (#370); a later round's checkpoint brief then quotes only the pointer

Since agent-fabric #370 (merged 2026-10-25, python-dev-03 j79, contract j375) post-review
posts a review of hundreds of paths: compact coverage block (MAX_BLOCK_CHARS 60000), a report
over GitHub's 65000 goes to a PR comment first and the review links it, and rename sources come
from `git diff --name-status -z`. Open limit named in the PR body: a moved report is not in the
review body, so the next round's checkpoint brief that quotes the previous review shows the
pointer, not the findings. A re-review of a large drain needs previous_findings passed as a file
until that is fixed. InterWeave #410 itself was replaced by #412 (merged 2026-10-24).

*Observed 2026-10-25 (fabric-coordinator)*
