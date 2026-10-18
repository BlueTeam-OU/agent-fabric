---
role: "web-dev"
class: index
description: "What web-dev knows and where it lives."
tier: 1
distilled_at: "2026-10-18"
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

- [`identities/roles/web-dev/brief.md`](identities/roles/web-dev/brief.md) — How web-dev works day to day, in any project: the browser implementation of designed behaviour, on agreed contracts, with browser state treated as a system, suites that tell the truth, and proof in a real browser.

## domain

- [`memory/domains/web-dev/domain/a-polyfill-can-depend-on-a-private-of-the-thing-it-patches.md`](memory/domains/web-dev/domain/a-polyfill-can-depend-on-a-private-of-the-thing-it-patches.md) — when a dependency bump breaks a DOM API, check whether the test harness — not the library — implements it, by reading a private
- [`memory/domains/web-dev/domain/act-warnings-shared-store.md`](memory/domains/web-dev/domain/act-warnings-shared-store.md) — Resetting a useSyncExternalStore-backed module in afterEach before Testing Library's cleanup() causes a React 'not wrapped in act' warning
- [`memory/domains/web-dev/domain/console-error-printf-args.md`](memory/domains/web-dev/domain/console-error-printf-args.md) — React's console.error calls pass a printf-style template plus separate substitution arguments, not an interpolated string
- [`memory/domains/web-dev/domain/count-polls-on-the-network-log.md`](memory/domains/web-dev/domain/count-polls-on-the-network-log.md) — to count how often a page polls a URL, read Playwright's network log; performance resource entries cap at 250 and a Vite dev page fills them, so they read as zero
- [`memory/domains/web-dev/domain/jsdom-raf-timing.md`](memory/domains/web-dev/domain/jsdom-raf-timing.md) — jsdom's requestAnimationFrame fires on a ~16ms setInterval, not a microtask, and races React state assertions
- [`memory/domains/web-dev/domain/keeps-it-on-screen-means-node-identity.md`](memory/domains/web-dev/domain/keeps-it-on-screen-means-node-identity.md) — A test that a surface "survives" a state change must assert DOM node identity — findability passes through a full remount.
- [`memory/domains/web-dev/domain/malformed-served-instant-is-error-not-absence.md`](memory/domains/web-dev/domain/malformed-served-instant-is-error-not-absence.md) — A served date/time that does not parse: how NaN slips through comparisons, clamps and Intl into 'Down for NaN d', and what to render instead
- [`memory/domains/web-dev/domain/per-call-mutate-callbacks-are-dropped.md`](memory/domains/web-dev/domain/per-call-mutate-callbacks-are-dropped.md) — a write's outcome toast in mutate(vars, {onError}) is lost when the page unmounts or a second mutate starts; put it on the hook and pin it with an unmount test
- [`memory/domains/web-dev/domain/react-refresh-export-rule.md`](memory/domains/web-dev/domain/react-refresh-export-rule.md) — ESLint's react-refresh/only-export-components rejects a file that exports both a component and a plain function/hook/constant
- [`memory/domains/web-dev/domain/responsive-overflow-css.md`](memory/domains/web-dev/domain/responsive-overflow-css.md) — Preventing horizontal overflow from images and long unbreakable heading tokens needs explicit CSS, not just max-width
- [`memory/domains/web-dev/domain/rtl-text-matching.md`](memory/domains/web-dev/domain/rtl-text-matching.md) — React Testing Library's getByText cannot match a sentence split across sibling DOM nodes
- [`memory/domains/web-dev/domain/tanstack-invalidate-joins-first-read.md`](memory/domains/web-dev/domain/tanstack-invalidate-joins-first-read.md) — why invalidateQueries after a write can still show pre-write data — it joins a first read that has no data yet
- [`memory/domains/web-dev/domain/tanstack-staletime-vs-gctime.md`](memory/domains/web-dev/domain/tanstack-staletime-vs-gctime.md) — TanStack Query: what never serving a read from cache takes (staleTime and gcTime), and what unset refetchOn* options mean
- [`memory/domains/web-dev/domain/test-setup-must-separate-wrong-impl.md`](memory/domains/web-dev/domain/test-setup-must-separate-wrong-impl.md) — Why a test that survives a revert can still miss the scenario it names: the setup lets the wrong implementation pass too
- [`memory/domains/web-dev/domain/unknown-served-enum-renders-unknown.md`](memory/domains/web-dev/domain/unknown-served-enum-renders-unknown.md) — What a screen shows when the server sends a status, role or model value the client's closed set does not have yet
- [`memory/domains/web-dev/domain/vite-workspace-import-boundary.md`](memory/domains/web-dev/domain/vite-workspace-import-boundary.md) — Vite rejects a relative import that crosses the pnpm workspace package root, even though the target file exists on disk
- [`memory/domains/web-dev/domain/vitest-fake-timers-ordering.md`](memory/domains/web-dev/domain/vitest-fake-timers-ordering.md) — vi.useFakeTimers() cannot advance a setTimeout already registered on the real clock
- [`memory/shared/domain-claude-code-attribution-reminder.md`](memory/shared/domain-claude-code-attribution-reminder.md) — The attribution key is written by runtime/claude-code/user-settings.py, run from tools/fabric/bootstrap.py (shared)

## solution

- [`.agent-fabric/memory/web-dev/solution.md`](.agent-fabric/memory/web-dev/solution.md) — A MapLibre paint colour taken from a gzapp design token must be converted to sRGB first — the tokens are OKLCH and MapLibre rejects the layer

## workflow

- [`.agent-fabric/memory/web-dev/workflow/agent-store-writes-via-settings-put.md`](.agent-fabric/memory/web-dev/workflow/agent-store-writes-via-settings-put.md) — How to put files (persona, avatar) into my own fabric-agent-<id> repository — never by cloning it
- [`.agent-fabric/memory/web-dev/workflow/background-run-exit-is-last-command.md`](.agent-fabric/memory/web-dev/workflow/background-run-exit-is-last-command.md) — Running a PR watcher or any verdict-by-exit-code script in the harness's background mode: why the reported exit can lie
- [`.agent-fabric/memory/web-dev/workflow/finding-own-open-work.md`](.agent-fabric/memory/web-dev/workflow/finding-own-open-work.md) — How to find which of my changes are still open in a project when every agent commits under one GitHub author
- [`.agent-fabric/memory/web-dev/workflow/pr-status-names-its-head.md`](.agent-fabric/memory/web-dev/workflow/pr-status-names-its-head.md) — Before telling anyone a PR is green, reviewed or 'gate met': which head that was true of, and what a later push does to it
- [`.agent-fabric/memory/web-dev/workflow/workflow-carried-2026-10-12.md`](.agent-fabric/memory/web-dev/workflow/workflow-carried-2026-10-12.md) — Before reading gzapp code for a claim or a build, branch from origin/main — the local main checkout can be thousands of commits behind

## recall

- [`identities/roles/web-dev/recall.md`](identities/roles/web-dev/recall.md) — Where web-dev's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
