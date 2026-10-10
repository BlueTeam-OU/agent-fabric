---
role: "web-dev"
class: index
description: "What web-dev knows and where it lives."
tier: 1
distilled_at: "2026-10-10"
---

# web-dev — knowledge index

A session is given the charter and brief (in the launch prompt),
and the project's remit with a pointer to this index (from the
session-start hook) — nothing below. Open a slice when its cue
matches what you are doing; a `workflow` slice says how a kind of
work is done here, so read the matching ones before that work.
Paths are relative to this working copy; `../agent-fabric/` is the
control plane checked out beside it.

## charter

- [`identities/roles/web-dev/charter.md`](identities/roles/web-dev/charter.md) — The browser-facing sub-apps and the shared web package: components, data fetching, accessibility, styling, web tests.

## brief

- [`identities/roles/web-dev/brief.md`](identities/roles/web-dev/brief.md) — How web-dev works day to day, in any project: the browser sub-apps and their shared package; suites that tell the truth, strict typing, and the gap between green and right.

## domain

- [`memory/domains/web-dev/domain/a-polyfill-can-depend-on-a-private-of-the-thing-it-patches.md`](memory/domains/web-dev/domain/a-polyfill-can-depend-on-a-private-of-the-thing-it-patches.md) — when a dependency bump breaks a DOM API, check whether the test harness — not the library — implements it, by reading a private
- [`memory/domains/web-dev/domain/act-warnings-shared-store.md`](memory/domains/web-dev/domain/act-warnings-shared-store.md) — Resetting a useSyncExternalStore-backed module in afterEach before Testing Library's cleanup() causes a React 'not wrapped in act' warning
- [`memory/domains/web-dev/domain/console-error-printf-args.md`](memory/domains/web-dev/domain/console-error-printf-args.md) — React's console.error calls pass a printf-style template plus separate substitution arguments, not an interpolated string
- [`memory/domains/web-dev/domain/jsdom-raf-timing.md`](memory/domains/web-dev/domain/jsdom-raf-timing.md) — jsdom's requestAnimationFrame fires on a ~16ms setInterval, not a microtask, and races React state assertions
- [`memory/domains/web-dev/domain/keeps-it-on-screen-means-node-identity.md`](memory/domains/web-dev/domain/keeps-it-on-screen-means-node-identity.md) — A test that a surface "survives" a state change must assert DOM node identity — findability passes through a full remount.
- [`memory/domains/web-dev/domain/react-refresh-export-rule.md`](memory/domains/web-dev/domain/react-refresh-export-rule.md) — ESLint's react-refresh/only-export-components rejects a file that exports both a component and a plain function/hook/constant
- [`memory/domains/web-dev/domain/responsive-overflow-css.md`](memory/domains/web-dev/domain/responsive-overflow-css.md) — Preventing horizontal overflow from images and long unbreakable heading tokens needs explicit CSS, not just max-width
- [`memory/domains/web-dev/domain/rtl-text-matching.md`](memory/domains/web-dev/domain/rtl-text-matching.md) — React Testing Library's getByText cannot match a sentence split across sibling DOM nodes
- [`memory/domains/web-dev/domain/vite-workspace-import-boundary.md`](memory/domains/web-dev/domain/vite-workspace-import-boundary.md) — Vite rejects a relative import that crosses the pnpm workspace package root, even though the target file exists on disk
- [`memory/domains/web-dev/domain/vitest-fake-timers-ordering.md`](memory/domains/web-dev/domain/vitest-fake-timers-ordering.md) — vi.useFakeTimers() cannot advance a setTimeout already registered on the real clock
- [`memory/shared/domain-claude-code-attribution-reminder.md`](memory/shared/domain-claude-code-attribution-reminder.md) — The attribution key is written by runtime/claude-code/user-settings.py, run from tools/fabric/bootstrap.py (shared)

## recall

- [`identities/roles/web-dev/recall.md`](identities/roles/web-dev/recall.md) — Where web-dev's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
