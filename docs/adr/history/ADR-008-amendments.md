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
