# ADR-008 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-28 — The terminal keeps its scrollback

The owner asked why the coordinator's terminal had a working scrollbar
and the other agents' did not, then: "yes, include it".

The coordinator's `~/.claude/settings.json` carried `"tui": "default"`,
written by the `/tui default` command in its own session; no other
account had the key, so their harness used its full-screen renderer on
the terminal's alternate screen, which leaves the terminal nothing to
scroll back through. The settings writer now pins `tui` "default"
beside `showThinkingSummaries` and `verbose`, for the same reason: the
person operating the fleet reads a session from its terminal. It
reaches each account at its next bootstrap and each session at its next
launch.

### Amendment 2026-09-28 — The settings writer adds the memory-write check

The settings writer gains one hook entry, for ADR-013 rule 14's
write-time memory check: a PostToolUse `Write|Edit` hook at the
account's checkout path, identified by its script name so a moved
checkout is rewritten rather than duplicated, and every other hook the
account has kept. A hook added to user settings reaches running sessions
at the next upgrade, as a display key did the same day; a hook is
additive and changes nothing on screen.
