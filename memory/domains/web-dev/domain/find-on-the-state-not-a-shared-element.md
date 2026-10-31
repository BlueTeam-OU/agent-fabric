---
role: "web-dev"
class: domain
topic: "find-on-the-state-not-a-shared-element"
description: "findBy* must wait on an element unique to the target state; waiting on one the earlier state also renders, then getBy*, flakes under load"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "web-dev-02"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - aaf639213527aca7
---

## findBy* must wait on an element unique to the target state; waiting on one the earlier state also renders, then getBy*, flakes under load

A test that awaits `findByText(X)` and then reads the target state with `getByText(Y)` flakes when X is also rendered by an earlier state (e.g. a wordmark shared by the in-flight and failed branches): the find resolves early, and under load the state has not changed yet. Wait on an element only the target state renders, then assert the shared one synchronously.

**Why:** advertiser_web `src/auth/CallbackPage.test.tsx` went red under load in the PR #1141 review; fixed on j15 (commit 9f15bad6f). Delaying the mocked async 100ms (`setTimeout` in the mock) reproduced it every time.

**How to apply:** when you review or write a find-then-get sequence, ask whether the found element exists in every state the component passes through. Reproduce by delaying the mock, not by rerunning until it fails. Related: [[revert-test-reads-the-exit-not-the-tally]].

*References: revert-test-reads-the-exit-not-the-tally*

*Observed 2026-10-20 (web-dev)*
