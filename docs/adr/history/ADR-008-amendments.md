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

### Amendment 2026-10-01 — The fleet's auto-mode picture is written centrally

The owner asked for auto mode's setup to be done centrally, for every
agent, after the architect-cto login's own /auto-mode-setup proposed a
configuration. That proposal had read one project's transcripts. It
called the trusted repository private, so confidential material was
"fine to push", on a login that also pushes to agent-fabric, which is
public; and its Host containment entry came out six times over.

The harness's documentation settled where a fleet configuration goes:
the classifier reads `autoMode` from user and managed settings, never
from a project's settings. Managed settings would need root on every
host, and `/etc` does not persist in a Qubes AppVM; user scope is where
the fabric already writes its keys. Read back with `claude auto-mode
config` (2.1.282) from a scratch configuration: 21 environment entries,
the built-in 17 allow rules, 70 soft blocks plus the fleet's one, and 1
hard block plus the fleet's one.
