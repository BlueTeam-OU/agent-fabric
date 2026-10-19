---
role: "flutter-dev"
class: index
description: "What flutter-dev knows and where it lives."
tier: 1
distilled_at: "2026-10-18"
---

# flutter-dev — knowledge index

A session is given the charter and brief (in the launch prompt),
and the project's remit with a pointer to this index (from the
session-start hook) — nothing below. Open a slice when its cue
matches what you are doing; a `workflow` slice says how a kind of
work is done here, so read the matching ones before that work.
Paths are relative to this working copy; `../agent-fabric/` is the
control plane checked out beside it.

## charter

- [`identities/roles/flutter-dev/charter.md`](identities/roles/flutter-dev/charter.md) — The mobile clients and the shared package they depend on: screens, state, platform integration, client tests.

## brief

- [`identities/roles/flutter-dev/brief.md`](identities/roles/flutter-dev/brief.md) — How flutter-dev works day to day, in any project: the mobile clients, their shared package and what they need to run; interpretation stays off the client.

## domain

- [`memory/domains/flutter-dev/domain/a-green-check-is-evidence-only-once-seen-red.md`](memory/domains/flutter-dev/domain/a-green-check-is-evidence-only-once-seen-red.md) — A test or guard that passes proves nothing until it has been watched FAIL on the defect it guards — three times a green run was blind to the very change it was meant to catch.
- [`memory/domains/flutter-dev/domain/contract-closure-unevaluatedproperties.md`](memory/domains/flutter-dev/domain/contract-closure-unevaluatedproperties.md) — To tell whether a gzapp contract closes an object, check unevaluatedProperties — additionalProperties alone is wrong wherever the schema uses $ref.
- [`memory/domains/flutter-dev/domain/dart-gotchas.md`](memory/domains/flutter-dev/domain/dart-gotchas.md) — Dart null-aware map-entry operator binds to the value, not the key
- [`memory/domains/flutter-dev/domain/display-only-control-is-not-a-button.md`](memory/domains/flutter-dev/domain/display-only-control-is-not-a-button.md) — A control that only shows something (a compass, a status) must not be exposed to the screen reader as a button, and its tooltip must not merely repeat its label.
- [`memory/domains/flutter-dev/domain/flutter-attach-baseline.md`](memory/domains/flutter-dev/domain/flutter-attach-baseline.md) — flutter attach takes the CURRENT source as what the device runs: edits made before attaching never hot-reload; attach first, then edit
- [`memory/domains/flutter-dev/domain/flutter-no-guarded-zone-two-handlers.md`](memory/domains/flutter-dev/domain/flutter-no-guarded-zone-two-handlers.md) — A Flutter app's error sink is FlutterError.onError plus PlatformDispatcher.instance.onError — wrapping bootstrap in runZonedGuarded switches the second one off.
- [`memory/domains/flutter-dev/domain/i18n-slot-holds-a-bare-value.md`](memory/domains/flutter-dev/domain/i18n-slot-holds-a-bare-value.md) — A copy placeholder carries one bare value whose grammar the formatter fixes — a day or other qualifier gets its own key chosen by a local-date comparison, and the date skeleton is the locale holder's call because intl's forms carry case…
- [`memory/domains/flutter-dev/domain/import-skip-guard-checks-outputs.md`](memory/domains/flutter-dev/domain/import-skip-guard-checks-outputs.md) — A "skip if already built/imported" guard or a "current?" check must test what the step produces against its inputs, never a marker, the file's existence or its own hash — an older run leaves the same marker.
- [`memory/domains/flutter-dev/domain/killed-flutter-test-leaves-children.md`](memory/domains/flutter-dev/domain/killed-flutter-test-leaves-children.md) — A flutter test run killed by the harness (timeout, OOM) leaves its dartvm and frontend_server children alive for hours, and they are what starve the next run.
- [`memory/domains/flutter-dev/domain/locked-phone-ble-scan.md`](memory/domains/flutter-dev/domain/locked-phone-ble-scan.md) — A locked Android phone hears the beacon only with a FILTERED scan, renewed, and a beacon advertising fast enough — measured 2026-09-28 on the bench phone
- [`memory/domains/flutter-dev/domain/measurement-can-be-the-signature.md`](memory/domains/flutter-dev/domain/measurement-can-be-the-signature.md) — Before a number exonerates or explains, ask what mechanism produces it — a too-perfect value can be the defect's signature, and a correlated attribute can pose as the cause.
- [`memory/domains/flutter-dev/domain/next-calendar-day-not-24h.md`](memory/domains/flutter-dev/domain/next-calendar-day-not-24h.md) — "Tomorrow at the same wall clock" is DateTime(y, m, d + 1, h, min), never add(Duration(days: 1)) — and a test of it can only fail when run in a DST-observing zone.
- [`memory/domains/flutter-dev/domain/regex-source-scan-gotchas.md`](memory/domains/flutter-dev/domain/regex-source-scan-gotchas.md) — A quote-exclusion character class breaks on delimiter-swapped literals; use a tempered token, require unicode:true for \p{L}, and scan whole files for multi-line matches
- [`memory/domains/flutter-dev/domain/riverpod-testing.md`](memory/domains/flutter-dev/domain/riverpod-testing.md) — Riverpod 3.x FamilyNotifier test migration breaks silently, not loudly
- [`memory/domains/flutter-dev/domain/rule-over-data-count-whole-population.md`](memory/domains/flutter-dev/domain/rule-over-data-count-whole-population.md) — Before a predicate or exclusion rule over real data ships, count it over the whole dataset and read every exception — a sample lies, and an "exception" may be a convention.
- [`memory/domains/flutter-dev/domain/supplied-copy-is-byte-exact.md`](memory/domains/flutter-dev/domain/supplied-copy-is-byte-exact.md) — Locale copy can carry bytes an eye cannot check — a Cyrillic С that looks like Latin C, a no-break space before a unit or after № — so commit supplied strings by paste and verify the code points with a script.
- [`memory/domains/flutter-dev/domain/translated-text-wraps-never-ellipsises.md`](memory/domains/flutter-dev/domain/translated-text-wraps-never-ellipsises.md) — A localised label or step line wraps, never truncates with an ellipsis — the cut lands on the meaningful tail (the street name, the word itself), and ru/ka run longer than the English the layout was judged on.
- [`memory/shared/domain-claude-code-attribution-reminder.md`](memory/shared/domain-claude-code-attribution-reminder.md) — The attribution key is written by runtime/claude-code/user-settings.py, run from tools/fabric/bootstrap.py (shared)

## workflow

- [`.agent-fabric/memory/flutter-dev/workflow/jobs-chore-without-artifact.md`](.agent-fabric/memory/flutter-dev/workflow/jobs-chore-without-artifact.md) — recording a chore that lands nothing (e.g. a REPLY-EXPECTED: no broadcast's disk cleanup) in fabric-jobs — drop it with the reason, never mark it done
- [`.agent-fabric/memory/flutter-dev/workflow/resend-a-request-a-session-drained.md`](.agent-fabric/memory/flutter-dev/workflow/resend-a-request-a-session-drained.md) — A REQUEST whose recipient's session drained it and ended without replying is invisible to their next cursor — re-send it as the same ask naming the original MESSAGE-ID; after repeated silence send one consolidated list asking for the work…
- [`.agent-fabric/memory/flutter-dev/workflow/same-role-sibling-routing.md`](.agent-fabric/memory/flutter-dev/workflow/same-role-sibling-routing.md) — When a role has two holders, a request or "they wait on you" may concern the sibling's work; establish whose it is on origin before building or answering
- [`.agent-fabric/memory/flutter-dev/workflow/settle-meaning-before-requesting-copy.md`](.agent-fabric/memory/flutter-dev/workflow/settle-meaning-before-requesting-copy.md) — Before a copy REQUEST goes to three locale holders, settle with the meaning owner what each line tells the reader AND what the reader should do — otherwise every cold read reopens the meaning and each round costs three re-requests.
- [`.agent-fabric/memory/flutter-dev/workflow/supply-branch-shas-on-origin-and-ranges.md`](.agent-fabric/memory/flutter-dev/workflow/supply-branch-shas-on-origin-and-ranges.md) — In a supply hand-off, a sha is named only after `git ls-remote` shows it on origin, and the caller folds the NAMED sha after reading base..sha for commits that are not the supply.

## recall

- [`identities/roles/flutter-dev/recall.md`](identities/roles/flutter-dev/recall.md) — Where flutter-dev's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
