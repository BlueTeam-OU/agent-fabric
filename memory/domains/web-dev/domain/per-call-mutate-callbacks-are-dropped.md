---
role: "web-dev"
class: domain
topic: "per-call-mutate-callbacks-are-dropped"
description: "a write's outcome toast in mutate(vars, {onError}) is lost when the page unmounts or a second mutate starts; put it on the hook and pin it with an unmount test"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - b591606e0fc15eb8
---

## a write's outcome toast in mutate(vars, {onError}) is lost when the page unmounts or a second mutate starts; put it on the hook and pin it with an unmount test

TanStack Query runs the callbacks passed to `mutate(vars, {...})` only
while the calling observer is still mounted and its call is still the
latest one. The callbacks passed to `useMutation({...})` always run. So
an outcome the person must see (a refusal above all) goes on the hook,
and the per-call callbacks only drive caller-local state (close the
editor, clear a typed secret, navigate).

Two ways to lose it, and they need different evidence:
- **overlap**: one mutation shared by every row, a second act starts
  before the first reply. A dialog that is `busy` while a write is in
  flight cannot overlap, so only the next case applies there.
- **unmount**: the person leaves the page before the reply. No guard
  prevents this.

The test that holds it unmounts the component before the mock answers,
then asserts the toast. It fails against the per-call shape. A test that
waits for the reply while mounted passes with either shape and proves
nothing. Refresh the list `onSettled`, not only `onSuccess`, because a
refusal is how a stale row shows itself.

In gzapp this is the rule "A write's outcome rides on the mutation",
`apps/admin_web/CLAUDE.md` (154a007d8; gzapp#1081 review F1). Cite it;
don't restate it.

*Observed 2026-10-12 (web-dev)*
