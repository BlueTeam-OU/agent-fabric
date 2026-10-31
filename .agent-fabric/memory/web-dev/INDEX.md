---
role: "web-dev"
class: index
description: "What web-dev knows and where it lives."
tier: 1
distilled_at: "2026-10-31"
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

- [`memory/domains/web-dev/domain/a-green-vitest-run-can-exit-1.md`](memory/domains/web-dev/domain/a-green-vitest-run-can-exit-1.md) — Vitest run exits 1 with every test passing: read the 'Errors N error' line; a timer a provider never clears fires after jsdom teardown
- [`memory/domains/web-dev/domain/a-polyfill-can-depend-on-a-private-of-the-thing-it-patches.md`](memory/domains/web-dev/domain/a-polyfill-can-depend-on-a-private-of-the-thing-it-patches.md) — when a dependency bump breaks a DOM API, check whether the test harness — not the library — implements it, by reading a private
- [`memory/domains/web-dev/domain/act-warnings-shared-store.md`](memory/domains/web-dev/domain/act-warnings-shared-store.md) — Resetting a useSyncExternalStore-backed module in afterEach before Testing Library's cleanup() causes a React 'not wrapped in act' warning
- [`memory/domains/web-dev/domain/await-what-only-the-target-state-renders.md`](memory/domains/web-dev/domain/await-what-only-the-target-state-renders.md) — A findBy on an element two render branches share resolves on the earlier branch; the next getBy then races the re-render under load.
- [`memory/domains/web-dev/domain/axe-under-jsdom-and-state-markers.md`](memory/domains/web-dev/domain/axe-under-jsdom-and-state-markers.md) — axe in jsdom answers landmark-one-main / page-has-heading-one "incomplete" even for correct markup; a state audit needs a marker only that state renders, checked absent in the others
- [`memory/domains/web-dev/domain/console-error-printf-args.md`](memory/domains/web-dev/domain/console-error-printf-args.md) — React's console.error calls pass a printf-style template plus separate substitution arguments, not an interpolated string
- [`memory/domains/web-dev/domain/count-polls-on-the-network-log.md`](memory/domains/web-dev/domain/count-polls-on-the-network-log.md) — to count how often a page polls a URL, read Playwright's network log; performance resource entries cap at 250 and a Vite dev page fills them, so they read as zero
- [`memory/domains/web-dev/domain/find-on-the-state-not-a-shared-element.md`](memory/domains/web-dev/domain/find-on-the-state-not-a-shared-element.md) — findBy* must wait on an element unique to the target state; waiting on one the earlier state also renders, then getBy*, flakes under load
- [`memory/domains/web-dev/domain/hls-manifest-video-engine-and-csp.md`](memory/domains/web-dev/domain/hls-manifest-video-engine-and-csp.md) — Before rendering a video URL that may be an HLS manifest (.m3u8): which browsers play it in a bare <video src>, and what an MSE engine needs from CSP and CORS
- [`memory/domains/web-dev/domain/joined-localized-strings-are-a-key.md`](memory/domains/web-dev/domain/joined-localized-strings-are-a-key.md) — When a component would join two localized values (a label plus a summary, even screen-reader-only text): the join is a key with placeholders, not component punctuation
- [`memory/domains/web-dev/domain/jsdom-message-event-source.md`](memory/domains/web-dev/domain/jsdom-message-event-source.md) — testing postMessage source checks under jsdom — construct the MessageEvent, then defineProperty its source to the stand-in window
- [`memory/domains/web-dev/domain/jsdom-raf-timing.md`](memory/domains/web-dev/domain/jsdom-raf-timing.md) — jsdom's requestAnimationFrame fires on a ~16ms setInterval, not a microtask, and races React state assertions
- [`memory/domains/web-dev/domain/keeps-it-on-screen-means-node-identity.md`](memory/domains/web-dev/domain/keeps-it-on-screen-means-node-identity.md) — A test that a surface "survives" a state change must assert DOM node identity — findability passes through a full remount.
- [`memory/domains/web-dev/domain/keycloak-stepup-acr-values-alone.md`](memory/domains/web-dev/domain/keycloak-stepup-acr-values-alone.md) — OIDC step-up on Keycloak — prompt=login/max_age=0 re-asks the FIRST factor; acr_values alone + the realm's LoA max-age 0 asks only the second
- [`memory/domains/web-dev/domain/lock-on-what-this-component-submitted.md`](memory/domains/web-dev/domain/lock-on-what-this-component-submitted.md) — A UI lock derived from a shared session's status alone misfires when the component remounts over it or its draft drifts; key the lock on the value THIS component submitted, and clear it on the explicit release.
- [`memory/domains/web-dev/domain/malformed-served-instant-is-error-not-absence.md`](memory/domains/web-dev/domain/malformed-served-instant-is-error-not-absence.md) — A served date/time that does not parse: how NaN slips through comparisons, clamps and Intl into 'Down for NaN d', and what to render instead
- [`memory/domains/web-dev/domain/nested-strictmode-does-not-double-effects.md`](memory/domains/web-dev/domain/nested-strictmode-does-not-double-effects.md) — React 19 does not double-invoke effects of a StrictMode nested inside a tree mounting in the same render — a StrictMode-guard test must put it at the root
- [`memory/domains/web-dev/domain/per-call-mutate-callbacks-are-dropped.md`](memory/domains/web-dev/domain/per-call-mutate-callbacks-are-dropped.md) — a write's outcome toast in mutate(vars, {onError}) is lost when the page unmounts or a second mutate starts; put it on the hook and pin it with an unmount test
- [`memory/domains/web-dev/domain/popup-session-not-keyed-to-click-state.md`](memory/domains/web-dev/domain/popup-session-not-keyed-to-click-state.md) — a per-act object whose window a click opens must not be re-created by the state that same click sets — the swap drops the window it just opened
- [`memory/domains/web-dev/domain/react-refresh-export-rule.md`](memory/domains/web-dev/domain/react-refresh-export-rule.md) — ESLint's react-refresh/only-export-components rejects a file that exports both a component and a plain function/hook/constant
- [`memory/domains/web-dev/domain/responsive-overflow-css.md`](memory/domains/web-dev/domain/responsive-overflow-css.md) — Preventing horizontal overflow from images and long unbreakable heading tokens needs explicit CSS, not just max-width
- [`memory/domains/web-dev/domain/rtl-text-matching.md`](memory/domains/web-dev/domain/rtl-text-matching.md) — React Testing Library's getByText cannot match a sentence split across sibling DOM nodes
- [`memory/domains/web-dev/domain/tanstack-invalidate-joins-first-read.md`](memory/domains/web-dev/domain/tanstack-invalidate-joins-first-read.md) — why invalidateQueries after a write can still show pre-write data — it joins a first read that has no data yet
- [`memory/domains/web-dev/domain/tanstack-staletime-vs-gctime.md`](memory/domains/web-dev/domain/tanstack-staletime-vs-gctime.md) — TanStack Query: what never serving a read from cache takes (staleTime and gcTime), and what unset refetchOn* options mean
- [`memory/domains/web-dev/domain/test-setup-must-separate-wrong-impl.md`](memory/domains/web-dev/domain/test-setup-must-separate-wrong-impl.md) — Why a test that survives a revert can still miss the scenario it names: the setup lets the wrong implementation pass too
- [`memory/domains/web-dev/domain/unknown-served-enum-renders-unknown.md`](memory/domains/web-dev/domain/unknown-served-enum-renders-unknown.md) — What a screen shows when the server sends a status, role or model value the client's closed set does not have yet
- [`memory/domains/web-dev/domain/vite-workspace-import-boundary.md`](memory/domains/web-dev/domain/vite-workspace-import-boundary.md) — Vite rejects a relative import that crosses the pnpm workspace package root, even though the target file exists on disk
- [`memory/domains/web-dev/domain/vitest-coverage-withheld-on-failure.md`](memory/domains/web-dev/domain/vitest-coverage-withheld-on-failure.md) — measuring Vitest coverage on a loaded host — a run with any failed test prints no coverage report unless reportOnFailure is set
- [`memory/domains/web-dev/domain/vitest-fake-timers-ordering.md`](memory/domains/web-dev/domain/vitest-fake-timers-ordering.md) — vi.useFakeTimers() cannot advance a setTimeout already registered on the real clock
- [`memory/domains/web-dev/domain/vitest-worker-start-timeout-drops-files.md`](memory/domains/web-dev/domain/vitest-worker-start-timeout-drops-files.md) — Under host load, vitest 5 drops test files whose fork worker fails to start from the tally — coverage collapses while "Test Files N passed (N)"
- [`memory/shared/domain-claude-code-attribution-reminder.md`](memory/shared/domain-claude-code-attribution-reminder.md) — The attribution key is written by runtime/claude-code/user-settings.py, run from tools/fabric/bootstrap.py (shared)

## solution

- [`.agent-fabric/memory/web-dev/solution.md`](.agent-fabric/memory/web-dev/solution.md) — A MapLibre paint colour taken from a gzapp design token must be converted to sRGB first — the tokens are OKLCH and MapLibre rejects the layer

## workflow

- [`.agent-fabric/memory/web-dev/workflow/agent-store-writes-via-settings-put.md`](.agent-fabric/memory/web-dev/workflow/agent-store-writes-via-settings-put.md) — How to put files (persona, avatar) into my own fabric-agent-<id> repository — never by cloning it
- [`.agent-fabric/memory/web-dev/workflow/background-run-exit-is-last-command.md`](.agent-fabric/memory/web-dev/workflow/background-run-exit-is-last-command.md) — Running a PR watcher or any verdict-by-exit-code script in the harness's background mode: why the reported exit can lie
- [`.agent-fabric/memory/web-dev/workflow/ci-red-fixed-on-main-needs-a-fold.md`](.agent-fabric/memory/web-dev/workflow/ci-red-fixed-on-main-needs-a-fold.md) — A PR's check is red for a cause outside its diff and the fix is on main — a re-run will not turn it green; fold origin/main, push, re-arm
- [`.agent-fabric/memory/web-dev/workflow/finding-own-open-work.md`](.agent-fabric/memory/web-dev/workflow/finding-own-open-work.md) — How to find which of my changes are still open in a project when every agent commits under one GitHub author
- [`.agent-fabric/memory/web-dev/workflow/held-commit-gets-carriers-and-a-date.md`](.agent-fabric/memory/web-dev/workflow/held-commit-gets-carriers-and-a-date.md) — When a small finished fix cannot ship alone (under the work-commit floor, an i18n-only PR, a spend limit): how to hold it without letting it rot
- [`.agent-fabric/memory/web-dev/workflow/jobs-done-needs-evidence-at-switch.md`](.agent-fabric/memory/web-dev/workflow/jobs-done-needs-evidence-at-switch.md) — fabric-jobs done <id> with no artifact is accepted, but switch then refuses to leave it — record the evidence when closing, a REPLY as reply:<MESSAGE-ID>
- [`.agent-fabric/memory/web-dev/workflow/never-tmp-shared-across-logins.md`](.agent-fabric/memory/web-dev/workflow/never-tmp-shared-across-logins.md) — scratch output in a shell command — /tmp is shared by every login on the host; a fixed name can be another agent's file
- [`.agent-fabric/memory/web-dev/workflow/pr-status-names-its-head.md`](.agent-fabric/memory/web-dev/workflow/pr-status-names-its-head.md) — Before telling anyone a PR is green, reviewed or 'gate met': which head that was true of, and what a later push does to it
- [`.agent-fabric/memory/web-dev/workflow/repeat-a-transition-to-test-the-server-guard.md`](.agent-fabric/memory/web-dev/workflow/repeat-a-transition-to-test-the-server-guard.md) — When a screen sends a state transition (approve, publish, deprecate) or words a dialog about one: check the server refuses it from the wrong state before trusting the UI's hidden button
- [`.agent-fabric/memory/web-dev/workflow/workflow-carried-2026-10-12.md`](.agent-fabric/memory/web-dev/workflow/workflow-carried-2026-10-12.md) — Before reading gzapp code for a claim or a build, branch from origin/main — the local main checkout can be thousands of commits behind
- [`.agent-fabric/memory/web-dev/workflow/workflow-trigger-comments-move-with-workflow.md`](.agent-fabric/memory/web-dev/workflow/workflow-trigger-comments-move-with-workflow.md) — When devex-tooling changes a CI trigger that a web config comment names, let them edit the comment in the same commit series

## recall

- [`identities/roles/web-dev/recall.md`](identities/roles/web-dev/recall.md) — Where web-dev's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
