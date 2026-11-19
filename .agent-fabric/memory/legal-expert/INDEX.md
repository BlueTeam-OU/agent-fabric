---
role: "legal-expert"
class: index
description: "What legal-expert knows and where it lives."
tier: 1
distilled_at: "2026-11-17"
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

- [`memory/domains/legal-expert/domain/ai-act-omnibus-2026-1744.md`](memory/domains/legal-expert/domain/ai-act-omnibus-2026-1744.md) — AI Act application dates after the Digital Omnibus on AI, Regulation (EU) 2026/1744 — read before citing any AI Act date
- [`memory/domains/legal-expert/domain/bger-relevancy-host.md`](memory/domains/legal-expert/domain/bger-relevancy-host.md) — Reading Federal Supreme Court decisions (BGE) from source; www.bger.ch fails TLS verification, so use relevancy.bger.ch with curl and decode the page as latin-1
- [`memory/domains/legal-expert/domain/ch-co-361-362-lists.md`](memory/domains/legal-expert/domain/ch-co-361-362-lists.md) — Swiss CO Art. 361 (26 items) / 362 (60 items) mandatory lists read DE/FR/IT on Fedlex, status 1 Oct 2026; plus provisions mandatory by own wording (335a, 335c(2), 324a(4), 321c(3), 129); read 2026-11-11
- [`memory/domains/legal-expert/domain/ch-employment-reclassification-and-pila-121.md`](memory/domains/legal-expert/domain/ch-employment-reclassification-and-pila-121.md) — Swiss test for reclassifying a consultant as an employee (Art. 319 CO, BGE), and why a choice of the employer's law holds before a Swiss court (PILA Art. 121(3), no favourability); read 2026-11-11
- [`memory/domains/legal-expert/domain/ch-treaty-precedence.md`](memory/domains/legal-expert/domain/ch-treaty-precedence.md) — Swiss law on a treaty provision against a federal act: the self-executing test, Art. 190 BV, precedence of international law, the Schubert exception and its limits (FZA, human rights)
- [`memory/domains/legal-expert/domain/fadp-art14-representative-reading.md`](memory/domains/legal-expert/domain/fadp-art14-representative-reading.md) — Whether a controller abroad needs a Swiss representative (DSG Art. 14), and how a notice names the FDPIC (a report, not a complaint) — read from Fedlex 2026-11-09
- [`memory/domains/legal-expert/domain/fdpic-scc-recognition-conditional.md`](memory/domains/legal-expert/domain/fdpic-scc-recognition-conditional.md) — Whether the EU 2021 SCCs carry Swiss data under Art. 16(2)(d) DSG — FDPIC recognition is conditional on Swiss adaptations; where to read it; DPF list not queryable here
- [`memory/domains/legal-expert/domain/georgian-legal-usage.md`](memory/domains/legal-expert/domain/georgian-legal-usage.md) — Georgian legal wording traps — calques and near-synonyms that change legal effect (ავტორიტეტული, შეიძლება, ამოქმედება, თანამდებობის პირი, მესაკუთრე…)
- [`memory/domains/legal-expert/domain/instrument-binding-shared-text.md`](memory/domains/legal-expert/domain/instrument-binding-shared-text.md) — How the shared legal-expert text states how an instrument binds (direct applicability vs direct effect; approximation binds only through the national act)
- [`memory/domains/legal-expert/domain/official-text-channels.md`](memory/domains/legal-expert/domain/official-text-channels.md) — How a session reads EU and Estonian legislation when EUR-Lex or Riigi Teataja refuse automated fetches
- [`memory/domains/legal-expert/domain/redacted-pil-labour-sources.md`](memory/domains/legal-expert/domain/redacted-pil-labour-sources.md) — Georgian PIL, labour-classification and judgment-recognition points read on Matsne 2026-11-11 (choice of law, court clauses, reciprocity, employee test)
- [`memory/domains/legal-expert/domain/redacted-sources-verified.md`](memory/domains/legal-expert/domain/redacted-sources-verified.md) — Georgian law points read on Matsne on 2026-10-17 (English versions): who is an advocate; what counts as official publication

## solution

- [`.agent-fabric/memory/legal-expert/solution/ai-act-scope-sentence-condition.md`](.agent-fabric/memory/legal-expert/solution/ai-act-scope-sentence-condition.md) — blueteam.ee disclaimer AI Act Scope sentence ('do not develop Annex III systems, for ourselves or for clients') holds only on the owner's 'no' of 2026-11-10
- [`.agent-fabric/memory/legal-expert/solution/client-contract-art25-commitment.md`](.agent-fabric/memory/legal-expert/solution/client-contract-art25-commitment.md) — Any client engagement contract draft must carry the AI Act Art 25(1) commitment that BlueTeam does not become provider of a client's high-risk AI system
- [`.agent-fabric/memory/legal-expert/solution/disclaimer-page-redraft-j29.md`](.agent-fabric/memory/legal-expert/solution/disclaimer-page-redraft-j29.md) — blueteam.ee disclaimer (service-scope) page plain-language redraft — where it is, what conditions it holds under, who places it
- [`.agent-fabric/memory/legal-expert/solution/privacy-notice-published-2026-11-11.md`](.agent-fabric/memory/legal-expert/solution/privacy-notice-published-2026-11-11.md) — blueteam.ee privacy notice published 11 Nov 2026; draft has no [FACT] left; a change now is a revision of a live notice
- [`.agent-fabric/memory/legal-expert/solution/solution-carried-2026-10-18.md`](.agent-fabric/memory/legal-expert/solution/solution-carried-2026-10-18.md) — Which providers hold Blueteam's personal data (email, hosting, accounting, payments, AI) and their GDPR role, as the owner stated on 2026-10-15

## workflow

- [`.agent-fabric/memory/legal-expert/workflow/disk-cleanup-at-job-end.md`](.agent-fabric/memory/legal-expert/workflow/disk-cleanup-at-job-end.md) — Before fabric-jobs switch, remove the job's worktree, sweep branches, clear scratch; say what and how much in evidence
- [`.agent-fabric/memory/legal-expert/workflow/fresh-session-before-new-job-writes.md`](.agent-fabric/memory/legal-expert/workflow/fresh-session-before-new-job-writes.md) — A job taken on after another ended in this session must start in a fresh session (fabric-jobs switch → fabric-fresh) before any commit or push; drafting first wastes a round
- [`.agent-fabric/memory/legal-expert/workflow/holder-addenda-ee-eu.md`](.agent-fabric/memory/legal-expert/workflow/holder-addenda-ee-eu.md) — Where legal-expert-ee-eu's Estonia/EU specifics live after ADR-060 (holder addenda), and their state
- [`.agent-fabric/memory/legal-expert/workflow/holder-launch-check.md`](.agent-fabric/memory/legal-expert/workflow/holder-launch-check.md) — How to check after a relaunch that holder addenda reached the launch prompt (launch-holder.json, launch-prompt.md)
- [`.agent-fabric/memory/legal-expert/workflow/inbox-exit-6-rearm.md`](.agent-fabric/memory/legal-expert/workflow/inbox-exit-6-rearm.md) — gzcoord-inbox exit 6 "schema version N, newer than this code's M" after a fabric upgrade — re-arm once; no checkout fast-forward job needed
- [`.agent-fabric/memory/legal-expert/workflow/inbox-watch-only-via-harness.md`](.agent-fabric/memory/legal-expert/workflow/inbox-watch-only-via-harness.md) — Start the GZCoord inbox watch only as a harness background Bash task; a detached one (& disown) cannot be killed and its delivery is lost
- [`.agent-fabric/memory/legal-expert/workflow/job-branch-feat-refused-use-for-user.md`](.agent-fabric/memory/legal-expert/workflow/job-branch-feat-refused-use-for-user.md) — In agent-fabric, the feat/ branch fabric-jobs gives a legal-expert job is refused by the commit hook; commit on <host>/<login>/for/user/<what>
- [`.agent-fabric/memory/legal-expert/workflow/jobs-deliver-reply-artifact.md`](.agent-fabric/memory/legal-expert/workflow/jobs-deliver-reply-artifact.md) — How to record a job delivered by message so fabric-jobs switch accepts it
- [`.agent-fabric/memory/legal-expert/workflow/jobs-question-blocker-never-clears.md`](.agent-fabric/memory/legal-expert/workflow/jobs-question-blocker-never-clears.md) — fabric-jobs block --on request:<id> where <id> is a QUESTION: the answer never clears it, and the job cannot be restarted
- [`.agent-fabric/memory/legal-expert/workflow/legal-wording-over-language-culture.md`](.agent-fabric/memory/legal-expert/workflow/legal-wording-over-language-culture.md) — On legal texts the owner ruled (2026-11-10, relayed by brand-comms-01) that legal-expert's wording wins over language-culture's optional spans
- [`.agent-fabric/memory/legal-expert/workflow/refused-shared-write-handoff-by-message.md`](.agent-fabric/memory/legal-expert/workflow/refused-shared-write-handoff-by-message.md) — What to do when my permission check refuses writing a deliverable into a shared folder another login reads
- [`.agent-fabric/memory/legal-expert/workflow/review-fix-branch-off-integrator-pr-head.md`](.agent-fabric/memory/legal-expert/workflow/review-fix-branch-off-integrator-pr-head.md) — Which base a contributor's review-fix for/ branch takes when its files exist only on the integrator's open PR
- [`.agent-fabric/memory/legal-expert/workflow/second-pass-before-proposing-words.md`](.agent-fabric/memory/legal-expert/workflow/second-pass-before-proposing-words.md) — Before sending proposed legal wording for adoption (an addendum line, a notice clause), do the independent second pass yourself: the act's scope, the exceptions, and the case law
- [`.agent-fabric/memory/legal-expert/workflow/watch-relay-down-single-process.md`](.agent-fabric/memory/legal-expert/workflow/watch-relay-down-single-process.md) — When gzcoord-inbox exits 5 (relay unreachable), wait for the relay and re-arm in ONE background command, not a poller plus a watch
- [`.agent-fabric/memory/legal-expert/workflow/workflow-carried-2026-10-18.md`](.agent-fabric/memory/legal-expert/workflow/workflow-carried-2026-10-18.md) — Reading Swiss federal law from Fedlex needs moli with --wait-selector '#art_1'; WebFetch gets only the splash screen, and moli's default wait a splash (1.1.19) or an empty dump (1.1.23)
- [`.agent-fabric/memory/legal-expert/workflow/workflow-charter-translation.md`](.agent-fabric/memory/legal-expert/workflow/workflow-charter-translation.md) — Translating a role's charter into Georgian: who writes it, who reviews it, how it is delivered
- [`.agent-fabric/memory/legal-expert/workflow/workflow-locale-render-review-cycle.md`](.agent-fabric/memory/legal-expert/workflow/workflow-locale-render-review-cycle.md) — Order of a Georgian locale render of a role text — two passes, cold read of the fix, then one delivery; budget cuts never drop a rule
- [`.agent-fabric/memory/legal-expert/workflow/workflow-watch-reaped-memory.md`](.agent-fabric/memory/legal-expert/workflow/workflow-watch-reaped-memory.md) — Inbox watch killed by Claude Code for low memory: re-arming is the fabric's standing rule; do it in the same turn, after checking free memory

## threads

- [`.agent-fabric/memory/legal-expert/threads/addenda-open-points.md`](.agent-fabric/memory/legal-expert/threads/addenda-open-points.md) — Open questions on my legal-expert-ge brief addendum, held for its next revision (company organs bullet)
- [`.agent-fabric/memory/legal-expert/threads/addenda-unverified-swiss-claims.md`](.agent-fabric/memory/legal-expert/threads/addenda-unverified-swiss-claims.md) — My ADR-060 holder addenda rest on three Swiss-law statements not yet read from Fedlex; verify them and correct the addendum if needed
- [`.agent-fabric/memory/legal-expert/threads/consultant-agreement-review-2026-11.md`](.agent-fabric/memory/legal-expert/threads/consultant-agreement-review-2026-11.md) — BlueTeam consultant (network participation) agreement review of 2026-11-11: where the opinion is, what is open, and why it is not in the public repo
- [`.agent-fabric/memory/legal-expert/threads/holder-addenda-reissued.md`](.agent-fabric/memory/legal-expert/threads/holder-addenda-reissued.md) — My -ch addenda were re-issued on 2026-10-18 against the jurisdiction-free shared legal-expert texts (ADR-060 stage 5)
- [`.agent-fabric/memory/legal-expert/threads/privacy-notice-swiss-f1-f3-open.md`](.agent-fabric/memory/legal-expert/threads/privacy-notice-swiss-f1-f3-open.md) — blueteam.ee privacy notice: section 10's Swiss OpenAI sentence dropped on the owner's F3 (8918d30d); what stays open
- [`.agent-fabric/memory/legal-expert/threads/privacy-page-native-read-rulings.md`](.agent-fabric/memory/legal-expert/threads/privacy-page-native-read-rulings.md) — j25: rulings on the blueteam.ee privacy page native read, applied in 71d0b5ff; Telegram kept; header fixed in 25a823fb

## recall

- [`identities/roles/legal-expert/recall.md`](identities/roles/legal-expert/recall.md) — Where legal-expert's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
