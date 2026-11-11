# ADR-067 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-11-10 — An owner may be a package

Rule 3 made any path a catalogue entry names that is not a tracked file
a finding. The job lifecycle's owner is a package, `tools/fabric/work/`,
of many modules, and the catalogue lint was changed on agent-fabric #520
to accept an owner named as its directory with the trailing slash when
a file under it is tracked; the rule was written only in the
catalogue's `_comment` and the lint's docstring. The blind review of
#520 (finding F5) found the record and the code disagreeing. Rule 3 now
says what the lint does. The slash is required, so a mistyped file name
never passes as a prefix; only an owner may be a directory, never a
checker or an exceptions file.
