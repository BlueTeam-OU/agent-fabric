# Fleet Deck: the states of an agent's tab

The deck's behaviour, as one state machine per agent's **harness pane**. Every state is defined by what the deck can observe, never by a guess. Every event names its source. Every transition names the deck's action.

This note is the contract for:
- the deck (herdr, rust-ui-dev);
- `moveto`'s modes and `fabric-resume` (agent-fabric, python-dev).

`session-recovery.md` is the plan this formalises; where the two differ, this note is right.

## What the deck observes

| signal | source | what it says |
|---|---|---|
| **pane** | herdr: the tab and its panes; a pane that is gone was closed by a person or its shell ended (herdr keeps neither the exit code nor the pane) | whether the harness pane exists |
| **foreground** | herdr `pane process-info`: the pane's foreground processes and their argv | moveto running in the pane (its outer `sudo`), or the operator's bare shell (moveto ended, with whatever code) |
| **harness here** | the descendants of the pane's foreground `sudo`, walked through `/proc/<pid>/stat` parent links (readable across logins on this host) | whether a harness (`launch.py` or `claude`) runs under this pane's moveto. Not the pane's foreground: sudo runs the account in a pty of its own (`use_pty`), so the harness is never in the pane's foreground group |
| **mode** | the foreground's argv: moveto hands off to `sudo … enter <dir> <title> [--wait|--resume|--watch]`, so the mode is its last argument; the deck reads it there, never from the screen, and so recovers it after its own restart | what the pane was asked to do |
| **live** | the state stream, the account's newest record: `sessions[]` | how many sessions are alive on the account, wherever they run, each `working`, `idle` or `blocked` |
| **record age** | the same record's `ts` | fresh (within two heartbeats, 20 min) or stale |
| **before** | the deck's own record of the last state it showed for the account, written on every change; with none (a first run), the newest stream record within two heartbeats that listed a live session | whether a session was alive before the restart. Not the stream's newest record: the sessions that die with herdr post their `live` = 0 before a restarting deck reads it |
| **resumable** | the record's `last_session` and `resumable` | whether `fabric-resume` will resume or start fresh |

**`live` counts sessions on the account, not in the pane.** A session started from another terminal shows in `live` while the deck's harness pane holds no session. The machine therefore keeps "a session runs here" and "a session runs on the account" apart (`ELSEWHERE`).

## States of the harness pane

| state | defined as | the deck shows |
|---|---|---|
| `ABSENT` | no tab for a placed agent | (nothing; it is created) |
| `DORMANT` | pane alive in mode `--wait`, `live` = 0 | dormant |
| `STARTING` | a `--resume` the deck itself started, `live` = 0, for less than `RESTORE_WAIT_S` (120 s). Enter in a `DORMANT` pane is not observable: that pane stays `DORMANT` until a session appears or moveto ends | restoring |
| `RUNNING(s)` | pane alive in a harness mode, `live` ≥ 1, record fresh; `s` is the state that most wants a person (blocked, then working, then idle) | resumed or fresh, then `s` |
| `ELSEWHERE` | `live` ≥ 1, but the deck's harness pane is `DORMANT`, or exited, or was never started | running elsewhere |
| `SHELL` | moveto still in the foreground with no session: the session ended and the account's shell remains (`live` = 0 after `RUNNING`) | shell |
| `FAILED` | `STARTING` for more than `RESTORE_WAIT_S`, or moveto ended (the pane back at the operator's shell) before any session appeared. The deck re-arms the pane with `--wait`, so it is one Enter from another try, and shows the failure until then | failed (moveto's last lines in the pane say why) |
| `STALE` | the account's newest record is older than two heartbeats | stale (overrides the others in the display, never in the decisions) |

**A plain shell is never a running agent.** An open moveto shell, with or without a person typing in it, is `SHELL` or `DORMANT`, never `RUNNING`.

## Events

| event | source |
|---|---|
| `enter` | a person presses Enter in a `DORMANT` pane. moveto `--wait` reads it; the deck does not see it, and no transition waits on it |
| `session-up` | the stream: `live` goes from 0 to ≥ 1 |
| `session-down` | the stream: `live` goes from ≥ 1 to 0 |
| `moveto-ended` | herdr: the harness pane's foreground is back at the operator's bare shell (moveto ended, any code) |
| `pane-gone` | herdr: the pane is no longer listed (a person closed it, or the operator's shell in it ended; the two are the same to the deck) |
| `timeout` | `RESTORE_WAIT_S` elapsed in `STARTING` |
| `restore` | the deck starts: after a deck, herdr or host restart |
| `stale` / `fresh` | the record's age crosses two heartbeats, either way |

## Transitions

| from | event | to | the deck does |
|---|---|---|---|
| `ABSENT` | `restore` | see **The restore decision** | create the tab: harness, shell and status panes |
| `DORMANT` | `session-up` | `RUNNING` when **harness here**, else `ELSEWHERE` | report it; on `ELSEWHERE`, re-arm the pane as a plain shell, so its Enter cannot start a second session. The deck cannot see Enter, but it sees what Enter started, among the processes under this pane's moveto |
| `DORMANT` | `moveto-ended` before any `session-up` | `FAILED` | re-arm `--wait`; show failed |
| `STARTING` | `session-up` | `RUNNING` | report the state to the panel |
| `STARTING` | `timeout`, or `moveto-ended` | `FAILED` | re-arm `--wait`; show failed; never start another session by itself |
| `RUNNING` | `session-down` with the pane alive | `SHELL` | report shell |
| `RUNNING` | `moveto-ended` | `DORMANT` if `live` = 0, `ELSEWHERE` if not | re-arm the pane with `--wait` (`DORMANT`) or as a plain shell (`ELSEWHERE`); only a restore resumes |
| `SHELL` | the person relaunches in the pane, then `session-up` | `RUNNING` | report it |
| `SHELL` | `moveto-ended` | `DORMANT` | re-arm the pane with `--wait` |
| `ELSEWHERE` | `session-down` | `DORMANT` | re-arm the harness pane with `--wait` (it held a plain shell while the session ran elsewhere) |
| `ELSEWHERE` | `session-up` in this pane (a person launched in its shell) | `RUNNING` | report it; the account then runs two sessions, by the person's choice |
| `FAILED` | `session-up` (the person pressed Enter in the re-armed pane) | `RUNNING` | report it |
| any | `pane-gone` (harness) | `ABSENT` until the next `restore` | nothing: the person chose the layout |
| shell or status pane | `pane-gone` | (no change) | re-created only at the next `restore` |

## The restore decision

At `restore`, for each placed agent whose harness pane is `ABSENT`, or is at the operator's bare shell, the deck takes `before` and `live`.

`live` is the account's newest record once the deck has waited one poll (`STATE_POLL_MS` plus a margin, 5 s) for the changes the restart caused, and only when that record is fresh (within two heartbeats). The control agent posts on every change and on a ten-minute heartbeat, so a record from before the restore is current when nothing has changed since. With no fresh record (the host is still starting, or the account's control agent is down), the deck waits up to `RESTORE_WAIT_S` for one, then decides `DORMANT`. An unknown `live` never leads to `--resume`.

- **`live` ≥ 1:** `ELSEWHERE`. The session survived (the deck or herdr restarted, not the host, or it runs in another terminal). The harness pane comes back as a plain `moveto` shell, never `--wait`: Enter must not start a second session.
- **`live` = 0, `before` had a session:** `STARTING` in mode `--resume`. It was running and died with the restart, so it comes back. A stale `before` counts: a host restart is exactly when records go stale.
- **`live` = 0, `before` had none, or no fresh record:** `DORMANT`, mode `--wait`.

The shell and status panes always come back live (`moveto <account>`, `moveto <account> --watch`).

After a deck-only restart, herdr and its panes survive. A harness pane with moveto in the foreground is classified from its argv's mode and the stream, and re-armed with nothing. Only a pane at the operator's bare shell, or a missing one, goes through the decision above.

## What must hold whatever the deck does (fabric side)

Not yet built: python-dev builds `moveto --wait`, `moveto --watch` and the refusal below, in its activation PR. Until they are on main, the deck builds against stand-ins and arms no pane with them.

- **No second session.** `fabric-resume` refuses to resume when the binding's session is alive on the account (`sessions[]` lists it), and says so. A deck mistake, or Enter pressed in two panes, never starts a duplicate.
- **One Enter, one activation.** moveto `--wait` reads one line, then does exactly `--resume`. End of input gives a plain shell, said.
- **The mode stays readable.** moveto's hand-off keeps the mode as the last argument of `sudo … enter`, so the deck can read it from the foreground's argv.
- **Nothing types into an account.** The deck acts only by starting a pane with a fixed mode (`--wait`, `--resume`, `--watch`, plain). No pane receives a person's text from the deck.

## Open questions

- **A harness pane closed by hand:** `ABSENT` until the next restore, or re-created dormant on the deck's next pass? The default is "until restore", as with the other panes: the deck does not fight a layout a person chose.
- **`FAILED`:** stays until a person acts. An automatic retry would hide a launcher that keeps failing.
