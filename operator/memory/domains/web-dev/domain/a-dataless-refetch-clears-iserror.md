---
role: "web-dev"
class: domain
topic: "a-dataless-refetch-clears-iserror"
description: TanStack Query v5 puts a query with no data back to pending on every refetch, so isError flickers false through each retry round; never gate an observer on it.
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 36f7e8b4d26645f3
---

## TanStack Query v5 puts a query with no data back to pending on every refetch, so isError flickers false through each retry round; never gate an observer on it.

In TanStack Query v5, a refetch of a query that has NO data resets its
status to `pending` (and clears `error`) for the whole fetch, retries
included. So `isError && data === undefined` is false during every retry
round of a failing query, and anything gated on it toggles off and on
each round.

Found on gzapp j48 (#1246 review F2, web-shared I18nProvider): an
observer revalidating the on-screen dictionary was `enabled` on
`switchFailed`. Re-enabling restarted its `refetchInterval`, and in
Chrome under the apps' retry policy the dictionary was asked for every
~67 s instead of 60 s. Unit tests with `retry: false` could not see it,
and with retries under jsdom the symptom was different (requests in
pairs, gaps of 6 s and 60 s), so a "max gap ≤ ceiling" assertion passed
against the broken gate.

**Why:** a flag that flickers with the fetch lifecycle is not a state.
**How to apply:** gate on a fact that stays put for the whole episode
(here: `query.data === undefined && retainedKey !== desired`), and pin
the cadence by EXACT gaps (`toEqual` every gap to the interval), which
catches both the extra and the missing request. Use a real browser for
timing claims ([[count-polls-on-the-network-log]]).

*References: count-polls-on-the-network-log*

*Observed 2026-11-11 (web-dev)*
