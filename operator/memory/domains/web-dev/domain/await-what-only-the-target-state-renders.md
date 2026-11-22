---
role: "web-dev"
class: domain
topic: "await-what-only-the-target-state-renders"
description: "A findBy on an element two render branches share resolves on the earlier branch; the next getBy then races the re-render under load."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - a23e77c436eaa6b1
---

## A findBy on an element two render branches share resolves on the earlier branch; the next getBy then races the re-render under load.

Await the text only the target state renders, then getBy what it shares
with other states. Awaiting a shared element (a wordmark in both the
in-flight and the failed branch) resolves on whichever branch is on
screen first, and the following synchronous getBy loses the race only
under host load — passes alone, fails in multi-file runs.

**Why:** advertiser_web CallbackPage.test.tsx failed this way at load 31
(2026-10-11); it was filed as a "1 s findBy" timeout, but the 5 s
budget was in force (probed `getConfig().asyncUtilTimeout` from both
`@testing-library/dom` and `/react`). Fixed in 3cdd12458.

**How to apply:** a load-only flake's real error text comes before any
fix — search past transcripts if the job saved none. Reproduce the race
by delaying the mocked promise ~100 ms (old test fails, new passes), and
when a mutation for the counterfactual replaces markup, keep each text
in its own element or the text matcher fails for the wrong reason.
Related: [[assert-on-recorded-state-not-call-count]].

*References: assert-on-recorded-state-not-call-count*

*Observed 2026-10-20 (web-dev)*
