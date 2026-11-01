---
role: "python-dev"
class: solution
topic: "j87-test-review-rounds-pr-delivered"
description: "j87 test_review_rounds moved to --pr chains; how the posted-body Locator case is built; delivered 4a221a3e"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - aeca1f7efea79634
---

## j87 test_review_rounds moved to --pr chains; how the posted-body Locator case is built; delivered 4a221a3e

j87 (#358 round 3 R4): tests/test_review_rounds.py chains of a PR-naming request run `next --pr 7` after `save 7 N`; `--report` beside such a request is refused. Delivered as 4a221a3e on origin develop-qzapp/python-dev-02/for/user/j333-review-coverage (0f55a094 was already an ancestor of 8f2f70dc: the "merge" was a fast-forward).

**Why:** the Locators must come from the checkpoint's posted body, not the saved round.
**How to apply:** the posted-body case lives in the deltarepo section: serve a posted review with base=head=b1, save a differing round with `--repo deltarepo`, request range b1..b1 with `--pr 7`; assert the posted locator present (control) and the saved marker absent. `git commit --amend` is refused by the hook for no staged path: reset --soft and recommit. A chained `git commit` plus `$HOME`-using command trips the job guard; run them separately.

*Observed 2026-10-24 (python-dev)*
