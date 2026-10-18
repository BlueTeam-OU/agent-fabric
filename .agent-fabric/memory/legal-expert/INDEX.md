---
role: "legal-expert"
class: index
description: "What legal-expert knows and where it lives."
tier: 1
distilled_at: "2026-10-18"
---

# legal-expert — knowledge index

A session is given the charter and brief (in the launch prompt),
and the project's remit with a pointer to this index (from the
session-start hook) — nothing below. Open a slice when its cue
matches what you are doing; a `workflow` slice says how a kind of
work is done here, so read the matching ones before that work.
Paths are relative to this working copy; `../agent-fabric/` is the
control plane checked out beside it.

## charter

- [`identities/roles/legal-expert/charter.md`](identities/roles/legal-expert/charter.md) — The fleet's legal expert for one jurisdiction, named by the login's suffix: what the law says about what the company does and what the fleet builds and publishes, cited from its source and dated, for the owner to decide.

## brief

- [`identities/roles/legal-expert/brief.md`](identities/roles/legal-expert/brief.md) — How legal-expert works day to day, for any jurisdiction: the question frozen first, every proposition traced to a dated source read, the layers of law kept apart, an opinion others can act on.

## domain

- [`memory/domains/legal-expert/domain/georgian-legal-usage.md`](memory/domains/legal-expert/domain/georgian-legal-usage.md) — Georgian legal wording traps — calques and near-synonyms that change legal effect (ავტორიტეტული, შეიძლება, ამოქმედება, თანამდებობის პირი, მესაკუთრე…)
- [`memory/domains/legal-expert/domain/instrument-binding-shared-text.md`](memory/domains/legal-expert/domain/instrument-binding-shared-text.md) — How the shared legal-expert text states how an instrument binds (direct applicability vs direct effect; approximation binds only through the national act)
- [`memory/domains/legal-expert/domain/official-text-channels.md`](memory/domains/legal-expert/domain/official-text-channels.md) — How a session reads EU and Estonian legislation when EUR-Lex or Riigi Teataja refuse automated fetches
- [`memory/domains/legal-expert/domain/redacted-sources-verified.md`](memory/domains/legal-expert/domain/redacted-sources-verified.md) — Georgian law points read on Matsne on 2026-10-17 (English versions): who is an advocate; what counts as official publication

## solution

- [`.agent-fabric/memory/legal-expert/solution.md`](.agent-fabric/memory/legal-expert/solution.md) — Which providers hold Blueteam's personal data (email, hosting, accounting, payments, AI) and their GDPR role, as the owner stated on 2026-10-15

## workflow

- [`.agent-fabric/memory/legal-expert/workflow/holder-addenda-ee-eu.md`](.agent-fabric/memory/legal-expert/workflow/holder-addenda-ee-eu.md) — Where legal-expert-ee-eu's Estonia/EU specifics live after ADR-060 (holder addenda), and their state
- [`.agent-fabric/memory/legal-expert/workflow/holder-launch-check.md`](.agent-fabric/memory/legal-expert/workflow/holder-launch-check.md) — How to check after a relaunch that holder addenda reached the launch prompt (launch-holder.json, launch-prompt.md)
- [`.agent-fabric/memory/legal-expert/workflow/refused-shared-write-handoff-by-message.md`](.agent-fabric/memory/legal-expert/workflow/refused-shared-write-handoff-by-message.md) — What to do when my permission check refuses writing a deliverable into a shared folder another login reads
- [`.agent-fabric/memory/legal-expert/workflow/review-fix-branch-off-integrator-pr-head.md`](.agent-fabric/memory/legal-expert/workflow/review-fix-branch-off-integrator-pr-head.md) — Which base a contributor's review-fix for/ branch takes when its files exist only on the integrator's open PR
- [`.agent-fabric/memory/legal-expert/workflow/workflow-carried-2026-10-18.md`](.agent-fabric/memory/legal-expert/workflow/workflow-carried-2026-10-18.md) — Reading Swiss federal law from Fedlex needs a JavaScript browser; WebFetch gets only the splash screen, so without moli every Swiss citation goes out unverified
- [`.agent-fabric/memory/legal-expert/workflow/workflow-charter-translation.md`](.agent-fabric/memory/legal-expert/workflow/workflow-charter-translation.md) — Translating a role's charter into Georgian: who writes it, who reviews it, how it is delivered
- [`.agent-fabric/memory/legal-expert/workflow/workflow-locale-render-review-cycle.md`](.agent-fabric/memory/legal-expert/workflow/workflow-locale-render-review-cycle.md) — Order of a Georgian locale render of a role text — two passes, cold read of the fix, then one delivery; budget cuts never drop a rule

## threads

- [`.agent-fabric/memory/legal-expert/threads/addenda-open-points.md`](.agent-fabric/memory/legal-expert/threads/addenda-open-points.md) — Open questions on my legal-expert-ge brief addendum, held for its next revision (company organs bullet)
- [`.agent-fabric/memory/legal-expert/threads/addenda-unverified-swiss-claims.md`](.agent-fabric/memory/legal-expert/threads/addenda-unverified-swiss-claims.md) — My ADR-060 holder addenda rest on three Swiss-law statements not yet read from Fedlex; verify them and correct the addendum if needed
- [`.agent-fabric/memory/legal-expert/threads/holder-addenda-reissued.md`](.agent-fabric/memory/legal-expert/threads/holder-addenda-reissued.md) — My -ch addenda were re-issued on 2026-10-18 against the jurisdiction-free shared legal-expert texts (ADR-060 stage 5)

## recall

- [`identities/roles/legal-expert/recall.md`](identities/roles/legal-expert/recall.md) — Where legal-expert's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
