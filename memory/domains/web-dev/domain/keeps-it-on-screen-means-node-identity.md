---
role: "web-dev"
class: domain
topic: "keeps-it-on-screen-means-node-identity"
description: "A test that a surface \"survives\" a state change must assert DOM node identity — findability passes through a full remount."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - de89da11733c88b1
---

## A test that a surface "survives" a state change must assert DOM node identity — findability passes through a full remount.

A component that returns `<><Notice/>{settled}</>` from one branch and
`settled` from another gives React two different element types at the
top of that subtree. Reconciling one against the other runs
`deleteRemainingChildren`: the whole wrapped surface is destroyed and
rebuilt, in **both** directions — entering the state and recovering from
it.

Visible cost: focus drops to `document.body` (gzapp registry rows are
`tabIndex: 0` via `hooks/useRowActivation.ts`), horizontal
`TableScroller` scroll resets, and any state inside the gate is lost.

**The testing rule.** `expect(screen.getByTestId("row")).toBeDefined()`
after the transition passes through a full remount — a rebuilt node is
findable. Capture the node before and assert `toBe` after:

```tsx
const original = screen.getByTestId("kept");
rerender(<AsyncState isError retainedData …>…</AsyncState>);
expect(screen.getByTestId("kept")).toBe(original);
```

Found by a blind review on gzapp #898 (F1, P2) and reproduced with that
probe before fixing; the fix is one tail return with the notice as a
sibling slot that turns on and off, so the children list stays a stable
two slots. The probe is now a test in
`apps/admin_web/src/components/ui/async-state.test.tsx`.

This is the same class as [[assert-on-recorded-state-not-call-count]]:
the assertion passes for a reason other than the behaviour it names.

*References: assert-on-recorded-state-not-call-count*

*Observed 2026-09-19 (web-dev)*
