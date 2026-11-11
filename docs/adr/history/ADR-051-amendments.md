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

### Amendment 2026-10-27 — The pin moves to moli 1.1.19

The owner asked devex-tooling (REQUEST 01a17c17, 2026-10-27) to move the
fleet's moli to the current upstream release, 1.1.19 (2026-10-21);
releases 1.1.16-1.1.19 carry fetch, navigation, frame and CDP fixes and
list no breaking change. Rule 1's pin moves with `projects/registry.json`
(#398): the archive's sha256 checked by devex-tooling and by the
coordinator against GitHub's published digest, the binary's sha256 the
coordinator's, of the member in that archive. The spike of 2026-10-10
(§1) measured 1.1.15 and stays its evidence; the checkbox and
drag-and-drop limits of rule 7 are unchanged by those releases' notes.

### Amendment 2026-11-11 — The pin moves to moli 1.1.23

The owner asked devex-tooling to prepare the move to the current
upstream release, 1.1.23 (2026-11-09), four releases past the pin
(REQUEST 01a1c620, 2026-11-10). Releases 1.1.20-1.1.23 move IndexedDB,
cookies and localStorage onto SQLite, fix request-header validation,
CORP before redirect and SameSite enforcement, and export markdown from
the live DOM and Shadow DOM. Rule 1's pin moves with
`projects/registry.json`: the archive's sha256 checked by devex-tooling
and by the coordinator against GitHub's published digest, the binary's
sha256 by both, of the member in that archive. devex-tooling's smoke,
1.1.19 against 1.1.23 with `fetch --dump markdown`, exited 0 on
example.com, a GitHub releases page and Fedlex with `--wait-selector`;
on Fedlex 1.1.23 returned text 1.1.19 dropped. One behaviour changed:
Fedlex without `--wait-selector` gave 1.1.19 a 1.2 KB splash and gives
1.1.23 an empty dump, still exit 0. The moli-web skill now says an
empty dump means the page was not ready. Rule 7's limits were not
re-measured.
