---
role: "web-dev"
class: domain
description: "jsdom's requestAnimationFrame fires on a ~16ms setInterval, not a microtask, and races React state assertions"
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-08-10"
origin:
  - clone_id: "clone-948c9fcd4da94057"
    host: "develop-qzapp"
derived_from:
  - 1e965e01a6ef7e31
  - 7b465cbdb303fddf
  - 9a2e6429e00f9eda
  - c4b8f60efdfa55d0
---

## jsdom's requestAnimationFrame fires on a ~16ms setInterval, not a microtask, and races React state assertions

jsdom only defines `requestAnimationFrame` when `window._pretendToBeVisual` is set (Vitest's jsdom environment sets this true by default), and its implementation backs rAF with `setInterval(..., 1000/60)` rather than firing on the next microtask/paint. Any component logic that defers work into a rAF callback (e.g. focusing or scrolling an element after a state update) can race a test's `waitFor()`, because `waitFor` can resolve on the state update alone before the rAF interval has ticked — a flake that reproduces under CI load but not locally, even under artificial CPU saturation. The durable fix is to flush one frame explicitly after the state-driven wait: `await act(async () => { await new Promise(requestAnimationFrame); })`. Because rAF callbacks fire FIFO, a self-queued frame resolving guarantees any earlier-queued component callback already ran — this is a construction-level fix, not a timing coincidence.
