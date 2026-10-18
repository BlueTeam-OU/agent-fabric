---
role: "fabric-coordinator"
class: workflow
topic: "fleet-shutdown-procedure"
description: "How the whole fleet was shut down on 2026-10-13 (no command exists): end sessions, deck, herdr, control agents — and how to bring it back"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b46322152d929bc1
---

## How the whole fleet was shut down on 2026-10-13 (no command exists): end sessions, deck, herdr, control agents — and how to bring it back

The owner shut the fleet down on 2026-10-13 (sessions "Immediate", then the deck and herdr, then
all 26 control agents, then my session). No fabric command does it: `fabric-ctl` has no stop op,
and its `restart` makes the launcher resume.

What worked, in order:
1. **Sessions**: each account's session runs over ssh from its deck "harness" pane. Map panes with
   `agent-fabric-fleetdeck pane list` (label `harness`) and `pane process-info --pane <id>`
   (the foreground `ssh … <login>@127.0.0.1 -- --resume`), SIGTERM those ssh clients (my uid).
   An outside SIGTERM leaves no restart marker, so the launcher does not resume. A session
   started by `moveto` from a herdr pty ends when herdr stops.
2. **Deck**: `fleet-deck stop` (controller only); **herdr**: `agent-fabric-fleetdeck server stop`.
   Check first that my own session is not in a herdr pane (mine ran in ptyxis).
3. **Control agents**: `fabric-host … run --as` has no user bus; `systemctl --machine=<u>@.host
   --user` fails here. Working form: `sudo -n -u <u> env XDG_RUNTIME_DIR=/run/user/<uid>
   DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/<uid>/bus systemctl --user stop
   agent-fabric-agentd.service`. Units stay enabled (back at boot).

**Why:** a gap — a fleet stop is a hand procedure; worth a `fabric-ctl all stop` or a script.
**How to apply:** to restart: the same sudo form with `start` per login (mine: plain
`systemctl --user start agent-fabric-agentd.service`), then `fleet-deck` (herdr, controller,
tab restore). Codex tokens synced before the stop expire 2026-10-22 15:46; the refresh runs in
my agentd. Related: [[own-account-upgrade]].

*References: own-account-upgrade*

*Observed 2026-10-13 (fabric-coordinator)*
