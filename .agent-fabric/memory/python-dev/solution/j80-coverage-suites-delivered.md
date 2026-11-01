---
role: "python-dev"
class: solution
topic: "j80-coverage-suites-delivered"
description: j80 — suites brought to the coverage schema, last_checkpoint_review, two items left with the coordinator
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 908b5b1310d17a48
---

## j80 — suites brought to the coverage schema, last_checkpoint_review, two items left with the coordinator

j80 delivered on for/user/j333-review-coverage (af077341). Traps: once a round's v2 review is posted, a re-review's SOURCE request no longer validates against the PR (checkpoint starts past its base) — review_rounds.next_request must validate it without `pr` (review_rounds.py is outside my entry: patch handed over, REPLY 01a16a99). dispatch_header now writes card_base/config that ledger.py does not copy: test_subagent_ledger stays red until the coordinator decides the row schema. A failed `git commit` leaves files staged: `git stash push <path>` then stashes the whole index; extract with `git diff stash^ stash -- path`.
**Why:** both found by running tests/run.sh with CI env after the three named suites were green.
**How to apply:** run the whole suite, not only the named suites, before delivering a schema change.

*Observed 2026-10-23 (python-dev)*
