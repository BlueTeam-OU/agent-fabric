---
role: "architect-cto"
class: index
description: "What architect-cto knows and where it lives."
tier: 1
distilled_at: "2026-10-18"
---

# architect-cto — knowledge index

A session is given the charter and brief (in the launch prompt),
and the project's remit with a pointer to this index (from the
session-start hook) — nothing below. Open a slice when its cue
matches what you are doing; a `workflow` slice says how a kind of
work is done here, so read the matching ones before that work.
Paths are relative to this working copy; `../agent-fabric/` is the
control plane checked out beside it.

## charter

- [`identities/roles/architect-cto/charter.md`](identities/roles/architect-cto/charter.md) — Owns what the system is supposed to be and the record of why: decision records, architecture documents, the authoritative wire contracts, cross-cutting policy.

## brief

- [`identities/roles/architect-cto/brief.md`](identities/roles/architect-cto/brief.md) — How architect-cto works day to day, in any project: owns the decisions and their delivery, writes the design first, sequences the roles, judges findings blind.

## domain

- [`memory/domains/architect-cto/domain/a-notice-content-is-a-function-of-its-merge-key.md`](memory/domains/architect-cto/domain/a-notice-content-is-a-function-of-its-merge-key.md) — a pushed state notice merged by (id, evaluated_at) must have every member recorded by the evaluation that stamped it; a member computed at dispatch changes under the key
- [`memory/domains/architect-cto/domain/adr-amendment-model-alternatives.md`](memory/domains/architect-cto/domain/adr-amendment-model-alternatives.md) — Correction for the field slice's allOf + not section — a domain slice carries its own pre-flight inline, never a [[link]] into a project corpus, and names a conformance helper's limit as a check to run, not a fact about one repo
- [`memory/domains/architect-cto/domain/antique-anthropic-code-review-surface.md`](memory/domains/architect-cto/domain/antique-anthropic-code-review-surface.md) — Antique is Anthropic's internal code review surface (2026), beside Scion source control; what is public about it and what is not
- [`memory/domains/architect-cto/domain/reflection-best-effort-ingest-caps-belong-in-the-contract.md`](memory/domains/architect-cto/domain/reflection-best-effort-ingest-caps-belong-in-the-contract.md) — On a best-effort ingest the endpoint's size caps are part of the wire shape (maxLength in the contract), because a client can only truncate to a bound it is told and an over-cap 400 under drop-on-failure is a silent loss
- [`memory/domains/architect-cto/domain/reflection-forged-identifier-guarantee-is-the-narrow-one.md`](memory/domains/architect-cto/domain/reflection-forged-identifier-guarantee-is-the-narrow-one.md) — 'A fabricated id names no row and is refused' overclaims when the id carries no table or namespace; state the narrower guarantee (unminted and non-colliding is refused; a colliding value is undetectable) and the rule that only the…
- [`memory/domains/architect-cto/domain/reflection-peer-defeatable-bound-is-the-contracts.md`](memory/domains/architect-cto/domain/reflection-peer-defeatable-bound-is-the-contracts.md) — A limit a peer's bytes can defeat into a process abort is the wire contract's bound, never a renderer's or parser's own; one number per kind of nesting, counted separately
- [`memory/domains/architect-cto/domain/reflection-sender-carrying-types-never-enter-the-rule-bearing-crate.md`](memory/domains/architect-cto/domain/reflection-sender-carrying-types-never-enter-the-rule-bearing-crate.md) — When a privacy rule is enforced by what a crate cannot depend on, satisfying a layering guard by moving types into that crate re-enables the rule; add a types-only crate instead
- [`memory/domains/architect-cto/domain/served-means-evidence-of-receipt-not-a-sent-response.md`](memory/domains/architect-cto/domain/served-means-evidence-of-receipt-not-a-sent-response.md) — a record that shows a client-held value to a third party must define "the client has it" as evidence of receipt (a later contact), never as "the server returned it" — ADR-078's call sign, 2026-10-15
- [`memory/shared/domain-claude-code-attribution-reminder.md`](memory/shared/domain-claude-code-attribution-reminder.md) — The attribution key is written by runtime/claude-code/user-settings.py, run from tools/fabric/bootstrap.py (shared)

## solution

- [`.agent-fabric/memory/architect-cto/solution.md`](.agent-fabric/memory/architect-cto/solution.md) — InterWeave: a stage opened beside a lower one is opened by a plan-section record, never by the workspace status, which names the lowest open stage because three guards read it as a number; a deferral to the parallel stage never fires

## rationale

- [`.agent-fabric/memory/architect-cto/rationale.md`](.agent-fabric/memory/architect-cto/rationale.md) — What the review pipeline costs and why (measured 2026-10-14): the fixed preamble re-sent per turn is 59-76% of a reviewer's prompt tokens; turns, not diff size, set the cost; re-reviews read more outside the fix range than inside it…

## workflow

- [`.agent-fabric/memory/architect-cto/workflow/authorizes-line-send-refused-by-auto-mode.md`](.agent-fabric/memory/architect-cto/workflow/authorizes-line-send-refused-by-auto-mode.md) — The auto-mode classifier refuses gzcoord-send of a DECISION carrying an AUTHORIZES line (boundary arm below minimum) as "CI Bypass"; the judgement is done in-session, the line reaches the arm only by the owner's hand
- [`.agent-fabric/memory/architect-cto/workflow/fold-by-merge-breaks-follow-on-a-rename.md`](.agent-fabric/memory/architect-cto/workflow/fold-by-merge-breaks-follow-on-a-rename.md) — A branch that renames a file must not fold origin/main by merge while main still has a file under the renamed-to name; git log --follow loses the history. Rebase instead, and measure in a scratch clone.
- [`.agent-fabric/memory/architect-cto/workflow/gzapp-active-contract-member-needs-dto-in-same-pr.md`](.agent-fabric/memory/architect-cto/workflow/gzapp-active-contract-member-needs-dto-in-same-pr.md) — In gzapp, adding a member to an ACTIVE closed contract fails the merge queue unless the backend DTO gains the member in the same PR — the PR's own CI skips the backend surface and hides it
- [`.agent-fabric/memory/architect-cto/workflow/gzapp-journey-call-sign-decision-2026-10-15.md`](.agent-fabric/memory/architect-cto/workflow/gzapp-journey-call-sign-decision-2026-10-15.md) — The owner's three choices behind gzapp ADR-078 (journey call sign, driver sees it only when the phone is silent, silence anchored on the ADR-077 wake) and why each alternative lost
- [`.agent-fabric/memory/architect-cto/workflow/gzcoord-info-skeleton-headings.md`](.agent-fabric/memory/architect-cto/workflow/gzcoord-info-skeleton-headings.md) — gzcoord-compose INFO renders CONTEXT:/NOTES: sections, not INFO:; a fill-in that targets a heading the skeleton lacks sends an empty, valid message
- [`.agent-fabric/memory/architect-cto/workflow/reflection-engine-behaviour-clause-is-decided-by-a-run-with-a-control.md`](.agent-fabric/memory/architect-cto/workflow/reflection-engine-behaviour-clause-is-decided-by-a-run-with-a-control.md) — A decision clause that rests on a third-party engine's behaviour is decided by a run with a control before the builder is written; the run's assumption is pinned in committed config with a citation and its harness lands under tools/ so an…
- [`.agent-fabric/memory/architect-cto/workflow/reflection-spike-verdict-cites-one-tool-build-per-run.md`](.agent-fabric/memory/architect-cto/workflow/reflection-spike-verdict-cites-one-tool-build-per-run.md) — Before citing a spike's verdict in a record, grep each run's evidence for the tool build it recorded against the summary's single claim; a self-updating tool splits a campaign silently

## recall

- [`identities/roles/architect-cto/recall.md`](identities/roles/architect-cto/recall.md) — Where architect-cto's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
