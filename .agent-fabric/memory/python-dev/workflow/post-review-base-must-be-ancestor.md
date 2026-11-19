---
role: "python-dev"
class: workflow
topic: "post-review-base-must-be-ancestor"
description: "fabric-pr post-review refuses a report whose base is not an ancestor of the head; merge origin/main into the branch BEFORE dispatching the review"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - bcfbb122eda67b5a
---

## fabric-pr post-review refuses a report whose base is not an ancestor of the head; merge origin/main into the branch BEFORE dispatching the review

j213 (#517): main moved after the branch was cut; the first review's base_sha (main tip) was not an ancestor of the head, so post-review refused and the whole review was wasted. Merge origin/main into the branch first, then render the brief and dispatch.
**Why:** the report is posted verbatim and its dispatch header pins base_sha; it cannot be edited.
**How to apply:** `git fetch && git merge origin/main`, push, then `fabric-review brief`. Also: a platform-smoke red with "python_pin: HTTP Error 504" is infrastructure; `gh run rerun <run> --failed`. Suites are plain scripts (`python3 tests/test_x.py`), not unittest/pytest. An open P3 in the chain blocks arm until `--defer "<head8>:F1" "<why>"`.

*Observed 2026-11-09 (python-dev)*
