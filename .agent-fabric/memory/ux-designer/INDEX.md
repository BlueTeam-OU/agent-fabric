---
role: "ux-designer"
class: index
description: "What ux-designer knows and where it lives."
tier: 1
distilled_at: "2026-10-31"
---

# ux-designer — knowledge index

A session is given the charter and brief (in the launch prompt),
and the project's remit with a pointer to this index (from the
session-start hook) — nothing below. Open a slice when its cue
matches what you are doing; a `workflow` slice says how a kind of
work is done here, so read the matching ones before that work.
Paths are relative to this working copy; `../agent-fabric/` is the
control plane checked out beside it.

## charter

- [`identities/roles/ux-designer/charter.md`](identities/roles/ux-designer/charter.md) — The fleet's user-experience designer: how a person meets, understands and operates what a project ships — flows, interactions, feedback, accessibility — specified for the developer who builds it and checked against the person who uses it.

## brief

- [`identities/roles/ux-designer/brief.md`](identities/roles/ux-designer/brief.md) — How ux-designer works day to day, in any project: design starts from the person's goal, is specified completely enough to build without guessing, rests on named evidence, and is verified in the running build against its own acceptance.

## domain

- [`memory/domains/ux-designer/domain/announce-once-undo-findable.md`](memory/domains/ux-designer/domain/announce-once-undo-findable.md) — One act is announced once: when focus moves to an element that states the result, no live announcement repeats it; then the Undo the announcement no longer names gets a hint placed by reading order, not by a visual landmark
- [`memory/domains/ux-designer/domain/awaited-answer-states.md`](memory/domains/ux-designer/domain/awaited-answer-states.md) — While an action waits for its answer: a waiting label that claims no outcome takes the button's place with focus, a progress mark that stays under reduced motion, and Back still closes the page, leaving the outcome to the next read
- [`memory/domains/ux-designer/domain/bounded-loss-is-a-choice.md`](memory/domains/ux-designer/domain/bounded-loss-is-a-choice.md) — when a memory bound must drop something the person cannot get back, no drop order fixes it; make crossing the bound the person's informed choice
- [`memory/domains/ux-designer/domain/case-tables-keyed-by-outcome.md`](memory/domains/ux-designer/domain/case-tables-keyed-by-outcome.md) — A spec's case table is keyed by the outcome observed, one row each, and its catch-all is checked both ways: no combination unnamed, no case another section requires swallowed
- [`memory/domains/ux-designer/domain/contrast-on-every-surface.md`](memory/domains/ux-designer/domain/contrast-on-every-surface.md) — Measure a mark's contrast against every surface it can sit on (snackbar, notice, bubble, selection), not only the screen background
- [`memory/domains/ux-designer/domain/declined-prompt-stays-declined.md`](memory/domains/ux-designer/domain/declined-prompt-stays-declined.md) — A system prompt the person cancelled is not raised again by itself on a return to the app; the blocked state shows why and keeps the action that raises it in view
- [`memory/domains/ux-designer/domain/every-count-variant.md`](memory/domains/ux-designer/domain/every-count-variant.md) — An element designed for many items (a notice above a list, a confirmation naming the item) is walked again with one item and with none: the container may not exist there, and the words it names may be barred in that mode
- [`memory/domains/ux-designer/domain/focus-table-in-spec.md`](memory/domains/ux-designer/domain/focus-table-in-spec.md) — When a spec names focus targets, list every case once in a single focus table in the acceptance section, each with its check, instead of scattering focus rules across sections
- [`memory/domains/ux-designer/domain/focus-target-not-drawn.md`](memory/domains/ux-designer/domain/focus-target-not-drawn.md) — Every focus rule has a fallback for a target that is not drawn when focus arrives (removed elsewhere, the list unreadable, the controls replaced): next row by last-drawn place, else the previous, else a fixed control; announce only what…
- [`memory/domains/ux-designer/domain/labels-as-whole-templates.md`](memory/domains/ux-designer/domain/labels-as-whole-templates.md) — Propose visible and spoken text as one whole template per case, never a prefix, a joined string or a template with optional parts, so a translation can reorder it
- [`memory/domains/ux-designer/domain/late-result-keeps-newer-feedback.md`](memory/domains/ux-designer/domain/late-result-keeps-newer-feedback.md) — When an action's feedback waits for an asynchronous answer, a newer action's feedback (and its Undo) is never replaced by the late result
- [`memory/domains/ux-designer/domain/picker-whole-word-prefixes.md`](memory/domains/ux-designer/domain/picker-whole-word-prefixes.md) — A narrowing word picker (type letters, pick from matches) must offer a typed whole word that is also a prefix of others, or such words can never be entered
- [`memory/domains/ux-designer/domain/refused-action-and-refused-undo.md`](memory/domains/ux-designer/domain/refused-action-and-refused-undo.md) — Every action that commits through a fallible store has a refused path, and so does its Undo; a refusal arriving after the visual commit returns the item in the state the backend reports then
- [`memory/domains/ux-designer/domain/refused-write-read-back.md`](memory/domains/ux-designer/domain/refused-write-read-back.md) — A refused write may already have happened: before a screen reports failure (or tells the person to discard something), it reads the stored state back
- [`memory/domains/ux-designer/domain/relative-day-rules-defined-once.md`](memory/domains/ux-designer/domain/relative-day-rules-defined-once.md) — A relative-date rule (Today, Yesterday, weekday) is defined once with its unit (calendar days, the device's time zone) and its future case; other sections refer to it, and every reference is true for every value
- [`memory/domains/ux-designer/domain/release-not-drop.md`](memory/domains/ux-designer/domain/release-not-drop.md) — a memory ceiling over rows that keep a stored copy is a silent release with load-on-reach gaps, never the limit row
- [`memory/domains/ux-designer/domain/screen-reader-text-matches-what-is-shown.md`](memory/domains/ux-designer/domain/screen-reader-text-matches-what-is-shown.md) — Compose a screen-reader description against the element's label and the screen: never repeat what the label says, speak what a symbol only shows, and say what the sighted person sees
- [`memory/domains/ux-designer/domain/strings-claim-only-what-is-true.md`](memory/domains/ux-designer/domain/strings-claim-only-what-is-true.md) — When specifying what a string must communicate, also write what it must not claim: no step the platform lacks, no scope wider than the action, no promise that will not come by itself
- [`memory/domains/ux-designer/domain/sweep-before-adopting-a-key.md`](memory/domains/ux-designer/domain/sweep-before-adopting-a-key.md) — Before specifying a text-matching rule (confusables, case folding, normalisation), sweep the whole data table; a fix proposed from a few examples hides gaps
- [`memory/domains/ux-designer/domain/thresholds-as-formulas.md`](memory/domains/ux-designer/domain/thresholds-as-formulas.md) — Write a compound threshold as an explicit formula (the larger of 40 % of the width and 96 dp) and give every 'that' its antecedent; a builder and a second-language reader both read a parenthesis two ways
- [`memory/domains/ux-designer/domain/undo-by-reverse-not-deferral.md`](memory/domains/ux-designer/domain/undo-by-reverse-not-deferral.md) — When specifying a snackbar Undo for a destructive action on mobile, run the action at once and undo by the reverse action, rather than deferring it until the snackbar closes
- [`memory/domains/ux-designer/domain/undo-restores-identity.md`](memory/domains/ux-designer/domain/undo-restores-identity.md) — An Undo that brings back something another system may already have seen restores the same record (its ids and bytes), never a new copy; ask the architecture role what the receiver deduplicates on
- [`memory/domains/ux-designer/domain/unknown-is-not-a-default.md`](memory/domains/ux-designer/domain/unknown-is-not-a-default.md) — A fact the client could not read (a failed read, a lost answer, a refused read) is shown as unknown with a line saying why, never as its default value; a retry that writes nothing keeps it unknown until a read shows it
- [`memory/domains/ux-designer/domain/wording-pass-keeps-conditions.md`](memory/domains/ux-designer/domain/wording-pass-keeps-conditions.md) — Read every language/English pass on a spec as a diff for meaning: a reworded if/else can drop a case

## solution

- [`.agent-fabric/memory/ux-designer/solution.md`](.agent-fabric/memory/ux-designer/solution.md) — InterWeave's UI is Slint 1.18: Text cannot be selected or copied, a layout cannot change with the window's width (binding loop), and StyledText's inline code font and background are not ours; a spec states the purpose beside any mechanism…

## workflow

- [`.agent-fabric/memory/ux-designer/workflow/arm-word-on-final-head.md`](.agent-fabric/memory/ux-designer/workflow/arm-word-on-final-head.md) — Ask for an arming word (AUTHORIZES) only on a head that will not move: every supply folded, review clean; after asking, a new ruling goes to the next branch and the developer builds on the reply
- [`.agent-fabric/memory/ux-designer/workflow/finding-says-what-has-to-change.md`](.agent-fabric/memory/ux-designer/workflow/finding-says-what-has-to-change.md) — A design review finding the developer is to build from states 'what has to change' as an observable result, choosing among the build options itself; a finding that only says what was seen leaves the developer waiting
- [`.agent-fabric/memory/ux-designer/workflow/product-question-with-built-reading.md`](.agent-fabric/memory/ux-designer/workflow/product-question-with-built-reading.md) — A product question to the architecture role carries the reading the spec is built on until the ruling, so the developer is not blocked and the answer changes one named line
- [`.agent-fabric/memory/ux-designer/workflow/scripted-input-on-shared-phone.md`](.agent-fabric/memory/ux-designer/workflow/scripted-input-on-shared-phone.md) — Scripted adb input on the shared test phone: check before every tap that the app holds focus, wait out system heads-ups, stop when a person uses the phone, read FLAG_SECURE before trusting a black capture, and log every anomaly with build…
- [`.agent-fabric/memory/ux-designer/workflow/verdict-per-condition-walked.md`](.agent-fabric/memory/ux-designer/workflow/verdict-per-condition-walked.md) — A device-review verdict passes only the conditions actually walked (screen x font scale x theme x state); anything unwalked is 'partly met' with the condition named, and a walk that needs a wipe, a revoked permission or the owner's unlock…

## recall

- [`identities/roles/ux-designer/recall.md`](identities/roles/ux-designer/recall.md) — Where ux-designer's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
