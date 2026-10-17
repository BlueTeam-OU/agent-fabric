# ADR-027 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-07 — The source locale has no bridge

§2 gains the source locale. The owner approved an English holder,
language-culture-en, for a project's English copy, and asked that it
write global English, a lingua franca. English is the fleet's own
language: the bridge exists to keep a holder from reasoning in English,
so it has no object for this one. The lint (locale_alignment_findings,
locale_file_findings) and the installer already treat an en-US locale
as carrying locale.json alone; the charter says which of its rules do
not apply. The blind review of the change asked that the record say so
too.

### Amendment 2026-10-16 — A charter is translated for a holder who works in that language

The owner, 2026-10-16, after legal-expert-ge was created with the request
that its charter be Georgian "like language-culture-ge": a role's charter
is translated only where its holder works in that language. A Georgian
legal expert reads Georgian law and must understand it in Georgian; a
legal expert for Estonia and the EU works from a corpus in English and
keeps the English charter. The translation is the role's own: its locale
holder writes it (rule 11 as it stood, and the carve-out of ADR-018 §5
rule 5), and `language-culture-<suffix>` reviews it in rule 3's two
passes. The first attempt had language-culture-ge render legal-expert's
charter, which the pre-commit hook refused and which fabric-coordinator
then committed in its place, against rule 11; that commit was reverted
on agent-fabric #283 and legal-expert-ge authors its own.

### Amendment 2026-10-16 — A holder may adopt language-culture's draft

#283's round-5 review found the Georgian legal-expert charter mostly language-culture-ge's text: legal-expert-ge committed it "from language-culture-ge's draft" (72641b50), while rule 11 said the holder "writes it". The owner, asked whether adopting the draft meets that, answered yes (2026-10-16). Rule 11 now says so: the holder may start from the language specialist's draft, owns what it commits under its own role, and names the draft in the commit, so the provenance a trailer cannot show is in the message. The reviewer is then the drafter, so its review is no longer a second reader's: the holder reads the whole committed text against the English source before the pull request, both of rule 3's passes still run on that text, and the last commit before the pull request says so beside naming the draft. An author is defined in the clause that admits the draft, the role that commits the text and answers for it, and the CEO's rule of 2026-09-17 keeps its own words (#288 review, rounds 1 and 2). The reading is fabric-coordinator's addition, from those reviews, to the owner's yes on adoption: without it a draft adopted unchanged is reviewed only by its drafter. It binds from this amendment on: the Georgian legal-expert charter's text as it stood (72641b50 through f184097e) predates it, and the reading is recorded, as rule 11 requires, in the last commit before legal-expert-ge's next pull request on that file.

### Amendment 2026-10-18 — The holder's locale, and the shared pieces once per language

ADR-060 §5 rule 8 separates a holder's language from its login: a holder's `holder.json` names its locale, and the login's suffix is only the fallback of a holder without one, so a rename no longer changes the language a session renders in. Rule 1 says so; rules 6 and 13 key the worker and the search setup on that locale, which the launcher resolves and passes on (`--locale` to the installer, `AGENT_FABRIC_LOCALE` to the search server). The second change was found on 2026-10-17: the header, team, memory and brief-missing renderings lived only in language-culture's own locale directory, so legal-expert-ge read those four sections in English. They now live once per language in `identities/prompt/locale/<suffix>/` (abdf5db8), a role's own rendering still wins (rule 9), and lint's coverage rule fails a role whose charter is rendered in a locale that lacks any of them. Who writes that directory is ADR-018 §5 rule 5's carve-out, amended the same day.
