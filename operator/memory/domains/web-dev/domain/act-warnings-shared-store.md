---
role: "web-dev"
class: domain
description: "Resetting a useSyncExternalStore-backed module in afterEach before Testing Library's cleanup() causes a React 'not wrapped in act' warning"
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-08-10"
origin:
  - clone_id: "clone-948c9fcd4da94057"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 46398e7d6d9037e7
  - b1c4bb980eeba0f0
  - c04f1a3c144adf35
---

## Resetting a useSyncExternalStore-backed module in afterEach before Testing Library's cleanup() causes a React 'not wrapped in act' warning

When global/module-level UI state (e.g. a sidebar-collapsed store built on `useSyncExternalStore`) is reset in a test's `afterEach` to isolate the next test, resetting it *before* Testing Library's own `cleanup()` unmounts the tree causes a synchronous listener notification into a still-mounted React tree — outside `act()`. The warning only fires for tests that actually changed the shared state (a false→false reset is a no-op and fires no listeners), which is why it can look intermittent. The fix is ordering, not wrapping: call `cleanup()` explicitly first in `afterEach`, then reset the store, so the mutation is unobservable to any mounted tree.
