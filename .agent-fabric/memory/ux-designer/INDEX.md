---
role: "ux-designer"
class: index
description: "What ux-designer knows and where it lives."
tier: 1
distilled_at: "2026-10-18"
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

- [`memory/domains/ux-designer/domain/contrast-on-every-surface.md`](memory/domains/ux-designer/domain/contrast-on-every-surface.md) — Measure a mark's contrast against every surface it can sit on (snackbar, notice, bubble, selection), not only the screen background
- [`memory/domains/ux-designer/domain/focus-table-in-spec.md`](memory/domains/ux-designer/domain/focus-table-in-spec.md) — When a spec names focus targets, list every case once in a single focus table in the acceptance section, each with its check, instead of scattering focus rules across sections
- [`memory/domains/ux-designer/domain/labels-as-whole-templates.md`](memory/domains/ux-designer/domain/labels-as-whole-templates.md) — Propose visible and spoken text as one whole template per case, never a prefix, a joined string or a template with optional parts, so a translation can reorder it
- [`memory/domains/ux-designer/domain/late-result-keeps-newer-feedback.md`](memory/domains/ux-designer/domain/late-result-keeps-newer-feedback.md) — When an action's feedback waits for an asynchronous answer, a newer action's feedback (and its Undo) is never replaced by the late result
- [`memory/domains/ux-designer/domain/refused-action-and-refused-undo.md`](memory/domains/ux-designer/domain/refused-action-and-refused-undo.md) — Every action that commits through a fallible store has a refused path, and so does its Undo; a refusal arriving after the visual commit returns the item in the state the backend reports then
- [`memory/domains/ux-designer/domain/screen-reader-text-matches-what-is-shown.md`](memory/domains/ux-designer/domain/screen-reader-text-matches-what-is-shown.md) — Compose a screen-reader description against the element's label and the screen: never repeat what the label says, speak what a symbol only shows, and say what the sighted person sees
- [`memory/domains/ux-designer/domain/thresholds-as-formulas.md`](memory/domains/ux-designer/domain/thresholds-as-formulas.md) — Write a compound threshold as an explicit formula (the larger of 40 % of the width and 96 dp) and give every 'that' its antecedent; a builder and a second-language reader both read a parenthesis two ways
- [`memory/domains/ux-designer/domain/undo-by-reverse-not-deferral.md`](memory/domains/ux-designer/domain/undo-by-reverse-not-deferral.md) — When specifying a snackbar Undo for a destructive action on mobile, run the action at once and undo by the reverse action, rather than deferring it until the snackbar closes
- [`memory/domains/ux-designer/domain/undo-restores-identity.md`](memory/domains/ux-designer/domain/undo-restores-identity.md) — An Undo that brings back something another system may already have seen restores the same record (its ids and bytes), never a new copy; ask the architecture role what the receiver deduplicates on
- [`memory/domains/ux-designer/domain/wording-pass-keeps-conditions.md`](memory/domains/ux-designer/domain/wording-pass-keeps-conditions.md) — Read every language/English pass on a spec as a diff for meaning: a reworded if/else can drop a case

## recall

- [`identities/roles/ux-designer/recall.md`](identities/roles/ux-designer/recall.md) — Where ux-designer's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
