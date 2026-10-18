---
role: "language-culture"
class: index
description: "What language-culture knows and where it lives."
tier: 1
distilled_at: "2026-10-18"
---

# language-culture — knowledge index

A session is given the charter and brief (in the launch prompt),
and the project's remit with a pointer to this index (from the
session-start hook) — nothing below. Open a slice when its cue
matches what you are doing; a `workflow` slice says how a kind of
work is done here, so read the matching ones before that work.
Paths are relative to this working copy; `../agent-fabric/` is the
control plane checked out beside it.

## charter

- [`identities/roles/language-culture/charter.md`](identities/roles/language-culture/charter.md) — The fleet's expert on language, translation, localization and local culture: what a text says in each language, what a market makes different, and localization as a contract — dictionaries, publication gate, fallback rules, validation.

## brief

- [`identities/roles/language-culture/brief.md`](identities/roles/language-culture/brief.md) — How language-culture works day to day, in any locale: reads the target before the source, treats a dictionary as a contract, knows whose input its files are, and proves the language it thinks in with notes.

## domain

- [`memory/domains/language-culture/domain/a-name-read-vs-a-name-copied.md`](memory/domains/language-culture/domain/a-name-read-vs-a-name-copied.md) — A personal name that is read aloud goes in Georgian script; one that is copied (a contact line beside an email and a domain) stays Latin — and an institution is called by the name it uses for itself, which is worth checking on its own site.
- [`memory/domains/language-culture/domain/absence-speaks-about-the-record.md`](memory/domains/language-culture/domain/absence-speaks-about-the-record.md) — In a Georgian status cell a bare participle takes the row's subject, the person; name the verb's object (the identity link), and bare "ბმა" reads as a hyperlink or an employment link
- [`memory/domains/language-culture/domain/call-sign-is-samodzakho-nishani.md`](memory/domains/language-culture/domain/call-sign-is-samodzakho-nishani.md) — ADR-078 call sign in Georgian: სამოძახო ნიშანი, the driver is told დაიძახეთ; "phone not responding" reads as an unanswered call (dba5b7207, 2026-10-16)
- [`memory/domains/language-culture/domain/instruction-doable-in-reader-situation.md`](memory/domains/language-culture/domain/instruction-doable-in-reader-situation.md) — an instruction in UI text (driver band, heads-up, rider hint) must be something its reader can do where they are — at the wheel, at a glance, without opening the app
- [`memory/domains/language-culture/domain/ka-clear-softens-a-destructive-act.md`](memory/domains/language-culture/domain/ka-clear-softens-a-destructive-act.md) — Georgian "გასუფთავება" (clear) reads as tidying a field or cache; on a button for a consequential act it softens it — name the act ("delete")
- [`memory/domains/language-culture/domain/ka-house-number-sign-is-convention.md`](memory/domains/language-culture/domain/ka-house-number-sign-is-convention.md) — In a Georgian address № before the house number is convention, not a data defect; the number sign may be stripped, a flat or block marker never
- [`memory/domains/language-culture/domain/ka-legal-english-calques.md`](memory/domains/language-culture/domain/ka-legal-english-calques.md) — იურიდიული ინგლისურის კალკები ქართულში — authoritative, operative, admitted, negotiated, entry into force/application, proposition/provision
- [`memory/domains/language-culture/domain/ka-may-vs-can-for-rights.md`](memory/domains/language-culture/domain/ka-may-vs-can-for-rights.md) — A right is "შეუძლია", not "შეიძლება", which reads as likelihood
- [`memory/domains/language-culture/domain/ka-owner-words-in-legal-text.md`](memory/domains/language-culture/domain/ka-owner-words-in-legal-text.md) — In a legal role's prompt, Georgian words for owner/finding/real read as legal terms — use "ეკუთვნის", "მიგნება", "საფუძვლიანი"
- [`memory/domains/language-culture/domain/ka-reaches-needs-mde.md`](memory/domains/language-culture/domain/ka-reaches-needs-mde.md) — Georgian "აღწევს" with a dative means attaining a goal; "reaches someone" needs -მდე
- [`memory/domains/language-culture/domain/ka-recurring-defect-families.md`](memory/domains/language-culture/domain/ka-recurring-defect-families.md) — The Georgian defect families that recur across every gzapi surface — check these first before reading a new text line by line
- [`memory/domains/language-culture/domain/ka-romanisation-without-apostrophes.md`](memory/domains/language-culture/domain/ka-romanisation-without-apostrophes.md) — A Georgian name is romanised for foreigners without apostrophes ([redacted], not K'ut'aisi); no letter rule recovers a borrowed name's source spelling
- [`memory/domains/language-culture/domain/ka-signature-is-kvali.md`](memory/domains/language-culture/domain/ka-signature-is-kvali.md) — signature (a betraying mark) — ხელმოწერა is a calque; the ge charter uses კვალი
- [`memory/domains/language-culture/domain/ka-tvis-before-participle-binds-to-it.md`](memory/domains/language-culture/domain/ka-tvis-before-participle-binds-to-it.md) — A -თვის noun right before a participle attaches to the participle, not to the verb before it
- [`memory/domains/language-culture/domain/locale-formatting-platform-limits.md`](memory/domains/language-culture/domain/locale-formatting-platform-limits.md) — The Georgian defect families that recur across every gzapi surface — check these first before reading a new text line by line
- [`memory/domains/language-culture/domain/miss-copy-with-two-causes.md`](memory/domains/language-culture/domain/miss-copy-with-two-causes.md) — Copy for a state whose two causes the client cannot tell apart says what we did, not the cause; advice that loops back on one cause is left out
- [`memory/domains/language-culture/domain/register-brand-shen-product-tkven.md`](memory/domains/language-culture/domain/register-brand-shen-product-tkven.md) — Brand surfaces address the rider as შენ (gzapi.brand 0007); product UI uses თქვენ, decided per surface by its owner with this role reviewing (0008); a quoted brand tagline keeps შენ.
- [`memory/domains/language-culture/domain/ru-marshrut-is-the-line-not-the-trip.md`](memory/domains/language-culture/domain/ru-marshrut-is-the-line-not-the-trip.md) — In Russian transit copy «маршрут» is a transit line/route, never the rider's trip; the trip is «поездка», the endpoint pair «откуда и куда»
- [`memory/domains/language-culture/domain/ru-merge-verb-vlivat.md`](memory/domains/language-culture/domain/ru-merge-verb-vlivat.md) — In Russian, merging a branch or PR is «вливать», never «сливать»: colloquially «сливать» means to fail or give up, the exact opposite
- [`memory/domains/language-culture/domain/ru-parenthesis-reads-as-restatement.md`](memory/domains/language-culture/domain/ru-parenthesis-reads-as-restatement.md) — A Russian parenthesis "(тот, что …)" reads as "that is"; put a narrower case in its own sentence
- [`memory/domains/language-culture/domain/ru-pronoun-after-telefon-passazhira.md`](memory/domains/language-culture/domain/ru-pronoun-after-telefon-passazhira.md) — After «Телефон пассажира…», Russian «его» reads as the phone; repeat the noun
- [`memory/domains/language-culture/domain/unknown-enum-value-is-neizvestno.md`](memory/domains/language-culture/domain/unknown-enum-value-is-neizvestno.md) — ru word for a value the build does not know (status, role, model, language, kind) — «Неизвестно», not «Не распознано»
- [`memory/domains/language-culture/domain/unknown-not-unrecognized.md`](memory/domains/language-culture/domain/unknown-not-unrecognized.md) — en word for a value the build does not know (status, role, enum, language, kind) — "Unknown", not "Unrecognized"
- [`memory/domains/language-culture/domain/verbatim-placeholder-carries-no-case.md`](memory/domains/language-culture/domain/verbatim-placeholder-carries-no-case.md) — A verbatim placeholder (stop name, line code) never takes a Georgian case ending; the case sits on a generic carrier noun and the name stays quoted in the nominative.
- [`memory/domains/language-culture/domain/welcome-copy-promises-no-completeness.md`](memory/domains/language-culture/domain/welcome-copy-promises-no-completeness.md) — Rider copy about the live map must not promise every vehicle — only those whose driver shares; a completeness finding is not closed by "the empty map explains itself elsewhere"
- [`memory/shared/domain-claude-code-attribution-reminder.md`](memory/shared/domain-claude-code-attribution-reminder.md) — The attribution key is written by runtime/claude-code/user-settings.py, run from tools/fabric/bootstrap.py (shared)

## solution

- [`.agent-fabric/memory/language-culture/solution.md`](.agent-fabric/memory/language-culture/solution.md) — header/team/memory/brief-missing-ის ქართული თარგმანი identities/prompt/locale/ge/-ში გადავიდა; ქარტია და ბრიფი როლთან რჩება

## workflow

- [`.agent-fabric/memory/language-culture/workflow/addenda-check-before-relaunch.md`](.agent-fabric/memory/language-culture/workflow/addenda-check-before-relaunch.md) — before you relaunch to pick up holder addenda, check fabric-status's addenda line; a session started after the store commit has already read them
- [`.agent-fabric/memory/language-culture/workflow/cold-read-explore-on-sonnet.md`](.agent-fabric/memory/language-culture/workflow/cold-read-explore-on-sonnet.md) — Холодное чтение готового текста — read-only Explore на model sonnet (не opus); locale-worker остаётся на opus
- [`.agent-fabric/memory/language-culture/workflow/cold-read-on-sonnet.md`](.agent-fabric/memory/language-culture/workflow/cold-read-on-sonnet.md) — how a cold read is dispatched — read-only Explore on model sonnet, never opus; report a miss with its example
- [`.agent-fabric/memory/language-culture/workflow/dictionary-value-has-readers-outside-the-dictionary.md`](.agent-fabric/memory/language-culture/workflow/dictionary-value-has-readers-outside-the-dictionary.md) — before changing or renaming a dictionary value or a UI term, find every reader of the old text — tests, comments, other values that quote it — and sweep by concept, not by string
- [`.agent-fabric/memory/language-culture/workflow/every-charter-change-gets-two-passes.md`](.agent-fabric/memory/language-culture/workflow/every-charter-change-gets-two-passes.md) — Every change to a translated charter gets the two passes, a one-clause change or a fix of my own finding included
- [`.agent-fabric/memory/language-culture/workflow/first-pass-fix-needs-source.md`](.agent-fabric/memory/language-culture/workflow/first-pass-fix-needs-source.md) — A first-pass finding from the worker is often right while its proposed fix, made without the source, changes the meaning
- [`.agent-fabric/memory/language-culture/workflow/first-pass-scope-to-changed-text.md`](.agent-fabric/memory/language-culture/workflow/first-pass-scope-to-changed-text.md) — A locale-worker first pass also flags file-wide terms; on a re-render, act only on findings in the changed text
- [`.agent-fabric/memory/language-culture/workflow/first-pass-settled-terms.md`](.agent-fabric/memory/language-culture/workflow/first-pass-settled-terms.md) — The Georgian first pass flags established fabric terms; a re-render does not change them
- [`.agent-fabric/memory/language-culture/workflow/fleet-jargon-in-public-copy.md`](.agent-fabric/memory/language-culture/workflow/fleet-jargon-in-public-copy.md) — when reading copy the fleet or a developer wrote — public pages, staff screens — check for the writer's own vocabulary (fleet words, API and code words) used as plain English
- [`.agent-fabric/memory/language-culture/workflow/key-value-true-in-every-state.md`](.agent-fabric/memory/language-culture/workflow/key-value-true-in-every-state.md) — before writing a key's value, read the code path that shows it — the value must be true in every state, platform and reader that path reaches
- [`.agent-fabric/memory/language-culture/workflow/lint-in-worktree-needs-fabric-flag.md`](.agent-fabric/memory/language-culture/workflow/lint-in-worktree-needs-fabric-flag.md) — in a worktree lint.py reads the main checkout unless --fabric is given — a false lag warning on the old digest
- [`.agent-fabric/memory/language-culture/workflow/locale-backtick-span-count.md`](.agent-fabric/memory/language-culture/workflow/locale-backtick-span-count.md) — a backticked span in a prompt translation must appear exactly as often as in its source; lint counts it
- [`.agent-fabric/memory/language-culture/workflow/locale-digest-is-body-only.md`](.agent-fabric/memory/language-culture/workflow/locale-digest-is-body-only.md) — A translation's translates_digest hashes the body, not the file; a lagging digest silently skips the token check; another role's locale is delivered in a REPLY
- [`.agent-fabric/memory/language-culture/workflow/locale-tags-byte-identical.md`](.agent-fabric/memory/language-culture/workflow/locale-tags-byte-identical.md) — In a translated prompt piece, angle-bracket tags (<First>, <role>) stay byte-identical — the lint counts them against the source
- [`.agent-fabric/memory/language-culture/workflow/message-body-quoted-heredoc.md`](.agent-fabric/memory/language-culture/workflow/message-body-quoted-heredoc.md) — A GZCoord message body with backticks or $ goes through a quoted heredoc only; substitute a variable afterwards, or the shell eats words and runs code spans
- [`.agent-fabric/memory/language-culture/workflow/name-the-pushed-commit.md`](.agent-fabric/memory/language-culture/workflow/name-the-pushed-commit.md) — before a REPLY names a delivered commit, read the branch head with git ls-remote; never let one script commit, push and send
- [`.agent-fabric/memory/language-culture/workflow/own-addenda-write-refused.md`](.agent-fabric/memory/language-culture/workflow/own-addenda-write-refused.md) — auto mode refuses this holder writing its own addendum file for install (Instruction Poisoning); report it and block, do not route around it
- [`.agent-fabric/memory/language-culture/workflow/prompt-drift-absent-means-none.md`](.agent-fabric/memory/language-culture/workflow/prompt-drift-absent-means-none.md) — no prompt-drift line in fabric-status means no drift, not a missing line
- [`.agent-fabric/memory/language-culture/workflow/recheck-my-own-fixes-next-round.md`](.agent-fabric/memory/language-culture/workflow/recheck-my-own-fixes-next-round.md) — Re-checking a re-render includes the lines my own earlier fixes produced, and the author's budget cuts; both introduce defects
- [`.agent-fabric/memory/language-culture/workflow/switch-needs-replies.md`](.agent-fabric/memory/language-culture/workflow/switch-needs-replies.md) — fabric-jobs switch refuses to leave a job while a REPLY-EXPECTED message is unanswered, and needs a memory change
- [`.agent-fabric/memory/language-culture/workflow/validate-i18n-not-runnable-here.md`](.agent-fabric/memory/language-culture/workflow/validate-i18n-not-runnable-here.md) — this account cannot run gzapp's i18n validator or the web suites (no pnpm, no node_modules); what to check by script instead and how to say it in a delivery
- [`.agent-fabric/memory/language-culture/workflow/variant-key-shares-sibling-words.md`](.agent-fabric/memory/language-culture/workflow/variant-key-shares-sibling-words.md) — writing a variant key (-no-sign, -no-x) beside a sibling: reuse the sibling's words, and a defect a reader finds is the sibling's too

## recall

- [`identities/roles/language-culture/recall.md`](identities/roles/language-culture/recall.md) — Where language-culture's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
