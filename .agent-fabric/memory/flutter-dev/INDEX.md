---
role: "flutter-dev"
class: index
description: "What flutter-dev knows and where it lives."
tier: 1
distilled_at: "2026-10-10"
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

- [`memory/domains/flutter-dev/domain/contract-closure-unevaluatedproperties.md`](memory/domains/flutter-dev/domain/contract-closure-unevaluatedproperties.md) — To tell whether a gzapp contract closes an object, check unevaluatedProperties — additionalProperties alone is wrong wherever the schema uses $ref.
- [`memory/domains/flutter-dev/domain/dart-gotchas.md`](memory/domains/flutter-dev/domain/dart-gotchas.md) — Dart null-aware map-entry operator binds to the value, not the key
- [`memory/domains/flutter-dev/domain/killed-flutter-test-leaves-children.md`](memory/domains/flutter-dev/domain/killed-flutter-test-leaves-children.md) — A flutter test run killed by the harness (timeout, OOM) leaves its dartvm and frontend_server children alive for hours, and they are what starve the next run.
- [`memory/domains/flutter-dev/domain/locked-phone-ble-scan.md`](memory/domains/flutter-dev/domain/locked-phone-ble-scan.md) — A locked Android phone hears the beacon only with a FILTERED scan, renewed, and a beacon advertising fast enough — measured 2026-09-28 on the bench phone
- [`memory/domains/flutter-dev/domain/regex-source-scan-gotchas.md`](memory/domains/flutter-dev/domain/regex-source-scan-gotchas.md) — A quote-exclusion character class breaks on delimiter-swapped literals; use a tempered token, require unicode:true for \p{L}, and scan whole files for multi-line matches
- [`memory/domains/flutter-dev/domain/riverpod-testing.md`](memory/domains/flutter-dev/domain/riverpod-testing.md) — Riverpod 3.x FamilyNotifier test migration breaks silently, not loudly
- [`memory/shared/domain-claude-code-attribution-reminder.md`](memory/shared/domain-claude-code-attribution-reminder.md) — The attribution key is written by runtime/claude-code/user-settings.py, run from tools/fabric/bootstrap.py (shared)

## recall

- [`identities/roles/flutter-dev/recall.md`](identities/roles/flutter-dev/recall.md) — Where flutter-dev's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
