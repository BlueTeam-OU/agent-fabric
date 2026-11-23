---
role: "web-dev"
class: domain
description: vi.useFakeTimers() cannot advance a setTimeout already registered on the real clock
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-08-10"
origin:
  - clone_id: "clone-948c9fcd4da94057"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 0e60a16b35269e24
  - c0e5d33c7c0fa182
  - fffc4d6e18e04db8
---

## vi.useFakeTimers() cannot advance a setTimeout already registered on the real clock

A `setTimeout` scheduled before `vi.useFakeTimers()` is called stays on the real clock; `vi.advanceTimersByTimeAsync()` has no effect on it. This matters for any effect-driven debounce (e.g. a reverse-geocode hint fired from a `useEffect` at mount): if a test renders the component, triggers the effect, and only afterwards calls `vi.useFakeTimers()`, the debounce timer is invisible to the fake clock and the assertion that follows passes for the wrong reason (the async work simply never fired) rather than because the guard being tested actually held. Confirmed via mutation testing in one sub-app's venue tests: the guard could be deleted entirely without the test failing until fake timers were installed *before* the triggering interaction instead of after.
