# ADR-051 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-11 — The scripted-browsing gate is met: moli serve behind @playwright/mcp, with limits

The gate §2 set for scripted browsing is met. The owner approved moli for
the agents' internet access on 2026-10-11, and domain-transit's test the same
day (@playwright/mcp 0.0.83 over CDP, three runs each against `moli serve
--layout` and Chrome 148, no model in the loop) is recorded in
`docs/live-checks/2026-10-10-moli-spike.md`, second section. On moli 11 of 11
flows and 3 of 3 reads passed, 22 of 24 tools (Chrome 24 of 24), the run took
2.1-2.5x as long, and a session held about 370 MB against about 990 MB.

What changed: scripted browsing through @playwright/mcp on a per-login `moli
serve --layout` bound to 127.0.0.1, started on demand and stopped after, is
allowed. Checkboxes (`browser_fill_form`'s checkbox field; a click on a 13x13
checkbox) and `browser_drag` fail on moli and go to Chrome; radio buttons were
not tested (domain-transit corrected its own recommendation, which had named
them) and go to Chrome until they are. Rule 3 stands: no permission rule allows
`moli serve`, a session starts it knowingly. Rule 4 loses its "not started
until the gate is met" clause; rule 7 is new. Title, status (Proposed) and
the pin are unchanged. The record is Proposed, so this edits it in place with
an amendment row, as README "Changing a record" asks; the history note keeps
the reasons.
