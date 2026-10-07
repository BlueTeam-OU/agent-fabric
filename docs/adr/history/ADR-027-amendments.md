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
