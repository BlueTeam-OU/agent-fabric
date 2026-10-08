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

Two observations decide a pane's state: whether moveto runs in it (**foreground**), and whether a harness runs under that moveto (**harness here**). The stream (`live`) only tells a pane with no harness whether the account's session runs somewhere else.

| state | defined as | the deck shows |
|---|---|---|
| `ABSENT` | no harness pane for a placed agent | (nothing; it is created at the next `restore`) |
| `RUNNING(s)` | moveto in the foreground and **harness here**; `s` is the account's state that most wants a person (blocked, then working, then idle) | `s` |
| `STARTING` | a `--resume` the deck itself started in this run of the deck, no harness here yet, for less than `RESTORE_WAIT_S` (120 s) | restoring |
| `ELSEWHERE` | moveto in the foreground, no harness here, `live` ≥ 1 | running elsewhere |
| `IDLE` | moveto in the foreground, no harness here, `live` = 0: waiting for Enter (`--wait`), or the account's shell after a session ended. The deck does not tell the two apart and needs not: each behaves the same on every event | dormant, or shell when the deck saw a session end in this pane |
| `FAILED` | an `IDLE` the deck re-armed after a failure: a `--resume` past `RESTORE_WAIT_S` with no harness, or moveto ending before any harness appeared. It behaves as `IDLE` on every event; only the display differs | failed (moveto's last lines in the pane say why) |
| `STALE` | the account's newest record is older than two heartbeats | stale (overrides the display, never a decision) |

**Re-arm, defined once.** To re-arm a harness pane is to start a fixed moveto command (`--wait`, `--resume`, or plain) in it while the pane is at the **operator's bare shell**, which is the deck's own shell and not an account's. The deck never re-arms while moveto is in the foreground: that would type into, or kill, what runs as the account. A pane that needs another mode while moveto runs keeps it until moveto ends.

## Events

| event | source |
|---|---|
| `enter` | a person presses Enter in an `IDLE` pane armed `--wait`. moveto reads it; the deck sees only what it starts (`harness-up`) |
| `harness-up` / `harness-down` | the process walk: a harness appears under, or disappears from, this pane's moveto |
| `session-up` / `session-down` | the stream: `live` goes from 0 to ≥ 1, or from ≥ 1 to 0 |
| `moveto-ended` | herdr: the pane's foreground is back at the operator's bare shell (moveto ended, any code) |
| `pane-gone` | herdr: the pane is no longer listed (a person closed it, or the operator's shell in it ended; the same to the deck) |
| `timeout` | `RESTORE_WAIT_S` elapsed in `STARTING` |
| `restore` | the deck starts, or reconnects to a herdr server it had lost |
| `stale` / `fresh` | the record's age crosses two heartbeats, either way |

## Transitions

| from | event | to | the deck does |
|---|---|---|---|
| `ABSENT` | `restore` | see **The restore decision** | create the tab: harness, shell and status panes |
| `IDLE`, `FAILED`, `ELSEWHERE`, `STARTING` | `harness-up` | `RUNNING` | report it. From `ELSEWHERE` the account then runs two sessions, by the person's choice |
| `IDLE`, `FAILED` | `session-up` without `harness-up` | `ELSEWHERE` | report only; re-arm nothing (moveto is in the foreground). An Enter in this pane is stopped by `fabric-resume`'s refusal (below) |
| `ELSEWHERE` | `session-down` | `IDLE` | report only; the pane keeps whatever moveto it holds |
| `RUNNING` | `harness-down` | `ELSEWHERE` if `live` ≥ 1, else `IDLE` (shown as shell) | report it; re-arm nothing: the account's shell is still in the pane |
| `STARTING` | `timeout` | `FAILED` | report failed; the `--resume` stays in the foreground, and the deck starts nothing more |
| any with moveto | `moveto-ended` before any `harness-up` since it was armed | `FAILED` | re-arm `--wait`; show failed |
| any with moveto | `moveto-ended` after a `harness-up` | `IDLE` | re-arm `--wait` if `live` = 0, plain if `live` ≥ 1 (in which case the state is `ELSEWHERE`) |
| any | `pane-gone` (harness) | `ABSENT` until the next `restore` | nothing: the person chose the layout |
| shell or status pane | `pane-gone` | (no change) | re-created only at the next `restore` |

**After a deck restart, or a reconnect, a surviving pane is classified, never re-armed.** With moveto in the foreground, it is `RUNNING` if harness here, else `ELSEWHERE` or `IDLE` by `live`. Its mode comes from the foreground's argv: the last argument of moveto's `sudo … enter` hand-off. That mode does not change after Enter, so it is never used to tell `IDLE` from anything. Only a pane at the operator's bare shell, or a missing one, goes through the restore decision.

## The restore decision

At `restore`, for each placed agent whose harness pane is `ABSENT`, or is at the operator's bare shell, the deck takes `before` and `live`.

`live` is the account's newest record once the deck has waited one poll (`STATE_POLL_MS` plus a margin, 5 s) for the changes the restart caused, and only when that record is fresh (within two heartbeats). The control agent posts on every change and on a ten-minute heartbeat, so a record from before the restore is current when nothing has changed since. With no fresh record (the host is still starting, or the account's control agent has been down for two heartbeats), the deck waits up to `RESTORE_WAIT_S` for one, then decides `IDLE`. An unknown `live` never leads to `--resume`. A control agent that died within the last two heartbeats leaves a record that looks fresh and may be wrong; there `fabric-resume`'s refusal, which reads the account's own session state rather than the stream, is what stops a second session.

- **`live` ≥ 1:** `ELSEWHERE`. The session survived (the deck or herdr restarted, not the host, or it runs in another terminal). The harness pane comes back as a plain `moveto` shell, never `--wait`: Enter must not start a second session.
- **`live` = 0, `before` had a session:** `STARTING`, the pane armed `--resume`. It was running and died with the restart, so it comes back. A stale `before` counts: a host restart is exactly when records go stale.
- **`live` = 0, `before` had none, or no fresh record:** `IDLE`, the pane armed `--wait`.

The shell and status panes always come back live (`moveto <account>`, `moveto <account> --watch`).

`before` is written when the deck shows a state, and is read only at `restore`. A deck that outlives herdr's server sees its panes go, then reconnects: that reconnect is a `restore`, with `before` as last shown before the loss.

## What must hold whatever the deck does (fabric side)

Not yet built: python-dev builds `moveto --wait`, `moveto --watch` and the refusal below, in its activation PR. Until they are on main, the deck builds against stand-ins and arms no pane with them.

- **No second session.** This is required before the deck arms any pane `--wait` or `--resume`: the deck cannot re-arm a pane whose moveto runs, so an Enter in an `ELSEWHERE` pane reaches `fabric-resume`. `fabric-resume` refuses to resume when the binding's session is alive on the account, read from the account's own session state as `runtime/control/sessions.mjs` counts it (a recorded pid alive with its start time), never from the stream, and says so. A deck mistake, or Enter pressed in two panes, never starts a duplicate.
- **One Enter, one activation.** moveto `--wait` reads one line, then does exactly `--resume`. End of input gives a plain shell, said.
- **The mode stays readable.** moveto's hand-off keeps the mode as the last argument of `sudo … enter`, so the deck can read it from the foreground's argv.
- **Nothing types into an account.** The deck starts a fixed moveto command (`--wait`, `--resume`, `--watch`, plain) only in its own bare shell, never while moveto runs (re-arm, above). No pane receives a person's text from the deck.

## Open questions

- **A harness pane closed by hand:** `ABSENT` until the next restore, or re-created dormant on the deck's next pass? The default is "until restore", as with the other panes: the deck does not fight a layout a person chose.
- **`FAILED`:** re-armed `--wait`, so one Enter retries; the deck never retries on its own. An automatic retry would hide a launcher that keeps failing.
