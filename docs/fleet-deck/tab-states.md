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
| **harness here** | the descendants of the pane's foreground `sudo`, walked through `/proc/<pid>/stat` parent links (readable across logins on this host: `/proc` is mounted without `hidepid`, read back by rust-ui-dev) | whether a harness (`launch.py` or `claude`) runs under this pane's moveto. Not the pane's foreground: sudo runs the account in a pty of its own (`use_pty`), so the harness is never in the pane's foreground group |
| **mode** | the foreground's argv: moveto hands off to `sudo … enter <dir> <title> [--wait|--resume|--watch]`, so the mode is its last argument; the deck reads it there, never from the screen, and so recovers it after its own restart | what the pane was asked to do |
| **live** | the state stream, the account's newest record: `sessions[]` | how many sessions are alive on the account, wherever they run, each `working`, `idle` or `blocked` |
| **server** | herdr's server instance: its pid (the socket peer, `SO_PEERCRED`; the server binds its socket itself and does not fork after) and its start time from `/proc/<pid>/stat`, compared between answers, and with a persisted fall's, as pid and raw start ticks (field 22); no wall-clock conversion is needed. The deck asks herdr every 2 s, with the process walk | whether two answers came from one server run. A change of instance is a `herdr-lost`, even when no request failed; so is an instance that cannot be read, on an answer that failed or succeeded (the server exited first); the next readable answer is the restore. herdr's live handoff starts a new process, so it is a change of instance too |
| **record age** | the same record's `ts` | fresh (within two heartbeats, 20 min) or stale |
| **before** | the deck's own record, persisted, of whether the account's session was running, meaning `live` ≥ 1 (wherever it ran). A rise is written at once. A fall is written only on positive evidence that herdr stayed up: a herdr request answered by the same server instance as the deck's last herdr answer before the fall (**server**), at or after the fall plus `SETTLE_S` (5 s). A rise cancels a pending fall. A fall seen while herdr is lost, or before the `restore` that ends a loss has decided, never settles. A pending fall is persisted with its time and the instance of the deck's last answer before it, so a deck that stops within the window settles it at its next start only if the current server is that same instance; with none (a first run), the newest stream record within two heartbeats that listed a live session | whether a session was alive before the restart. Not the stream's newest record: the sessions that die with herdr post their `live` = 0 before a restarting deck reads it |
| **resumable** | the record's `last_session` and `resumable` | whether `fabric-resume` will resume or start fresh |

**`live` counts sessions on the account, not in the pane.** A session started from another terminal shows in `live` while the deck's harness pane holds no session. The machine therefore keeps "a session runs here" and "a session runs on the account" apart (`ELSEWHERE`).

## States of the harness pane

Two observations decide a pane's state: whether moveto runs in it (**foreground**), and whether a harness runs under that moveto (**harness here**). The stream (`live`) only tells a pane with no harness whether the account's session runs somewhere else.

| state | defined as | the deck shows |
|---|---|---|
| `ABSENT` | no harness pane for a placed agent | (nothing; it is created at the next `restore`) |
| `RUNNING(s)` | moveto in the foreground and **harness here**; `s` is the account's state that most wants a person (blocked, then working, then idle) | `s` |
| `STARTING` | a `--resume` the deck itself started in this run of the deck, no harness here yet, `live` = 0, for less than `RESTORE_WAIT_S` (120 s). It takes precedence over `IDLE` while those hold | restoring |
| `ELSEWHERE` | moveto in the foreground, no harness here, `live` ≥ 1 | running elsewhere |
| `IDLE` | moveto in the foreground, no harness here, `live` = 0: waiting for Enter (`--wait`), or the account's shell after a session ended. The deck does not tell the two apart and needs not: each behaves the same on every event | dormant, or shell when the deck saw a session end in this pane |
| `FAILED` | a `--resume` the deck started in this run of the deck that produced no harness: past `RESTORE_WAIT_S`, or its moveto ended first, with `live` = 0. A `--wait` pane is never `FAILED`: the deck cannot see whether Enter was pressed, so a `--wait` moveto that ends is `IDLE`. It behaves as `IDLE` on every event until a `harness-up`; only the display differs | failed (moveto's last lines in the pane say why) |
| `STALE` | the account's newest record is older than two heartbeats | stale (overrides the display, never a decision) |

**Re-arm, defined once.** To re-arm a harness pane is to start a fixed moveto command (`--wait`, `--resume`, or plain) in it while the pane is at the **operator's bare shell**, which is the deck's own shell and not an account's. The deck never re-arms while moveto is in the foreground: that would type into, or kill, what runs as the account. A pane that needs another mode while moveto runs keeps it until moveto ends.

## Events

| event | source |
|---|---|
| `enter` | a person presses Enter in an `IDLE` pane armed `--wait`. moveto reads it; the deck sees only what it starts (`harness-up`) |
| `harness-up` / `harness-down` | the process walk, run on every stream event and every 2 s: a harness appears under, or disappears from, this pane's moveto. A `harness-up` within one stream poll of a `session-up` is the same session |
| `session-up` / `session-down` | the stream: `live` goes from 0 to ≥ 1, or from ≥ 1 to 0 |
| `moveto-ended` | herdr: the pane's foreground is back at the operator's bare shell (moveto ended, any code) |
| `pane-gone` | herdr: the pane is no longer listed (a person closed it, or the operator's shell in it ended; the same to the deck) |
| `timeout` | `RESTORE_WAIT_S` elapsed in `STARTING` |
| `herdr-lost` | the deck's connection to herdr's server fails or closes, or a request is answered by a different server instance than the one before. No fall of `before` settles until the `restore` that ends the loss has decided; falls pending at the loss, or seen during it, are discarded |
| `restore` | the deck starts, reconnects to a herdr server it had lost, or gets its first answer from a new server instance (that answer is the reconnect) |
| `stale` / `fresh` | the record's age crosses two heartbeats, either way |

## Transitions

| from | event | to | the deck does |
|---|---|---|---|
| `ABSENT` | `restore` | see **The restore decision** | create the tab: harness, shell and status panes |
| `IDLE`, `FAILED`, `ELSEWHERE`, `STARTING` | `harness-up` | `RUNNING` | report it. From `ELSEWHERE` the account then runs two sessions, by the person's choice |
| `IDLE`, `FAILED` | `session-up` without `harness-up` | `ELSEWHERE` | report only; re-arm nothing (moveto is in the foreground). An Enter in this pane is stopped by `fabric-resume`'s refusal (below) |
| `ELSEWHERE` | `session-down` | `IDLE` | report only; the pane keeps whatever moveto it holds |
| `RUNNING` | `harness-down` | `ELSEWHERE` if `live` ≥ 1, else `IDLE` (shown as shell) | report it; re-arm nothing: the account's shell is still in the pane |
| `STARTING` | `session-up` without `harness-up` | `ELSEWHERE` | report only: a session started elsewhere in the window, and this pane's `fabric-resume` refuses beside it |
| `STARTING` | `timeout` | `FAILED` | report failed; nothing is re-armed (moveto, by then the account's shell, still runs); the deck starts nothing more |
| any with moveto | `moveto-ended`, `live` ≥ 1 | `ELSEWHERE` | re-arm plain |
| any with moveto | `moveto-ended`, `live` = 0, the pane armed `--resume` by this run of the deck and no `harness-up` since | `FAILED` | re-arm `--wait` (but see **Loop guard**) |
| any with moveto | `moveto-ended`, `live` = 0, otherwise (a session ended, or a plain shell was left) | `IDLE` | re-arm `--wait` (but see **Loop guard**) |
| any | `pane-gone` (harness) | `ABSENT` until the next `restore` | nothing: the person chose the layout |
| shell or status pane | `pane-gone` | (no change) | re-created only at the next `restore` |

**Loop guard.** A moveto the deck started that ends within `LOOP_S` (3 s) of its start, twice in a row in the same pane, is not re-armed again, whichever of the two rows above it ended on: the pane is left at the bare shell and shown `FAILED` until the next `restore`. It stops a pane that fails at once from re-arming forever.

**Moveto in the foreground** is moveto's or `enter`'s process, or the `sudo` moveto hands off to; a pane for the deck's own login has no `sudo`, and its harness is then in the pane's own process tree, which the walk covers the same way.

**After a deck restart, or a reconnect, a surviving pane is classified, never re-armed.** With moveto in the foreground, it is `RUNNING` if harness here, else `ELSEWHERE` or `IDLE` by `live`. Its mode comes from the foreground's argv: the last argument of moveto's `sudo … enter` hand-off. That mode does not change after Enter, so it is never used to tell `IDLE` from anything. Only a pane at the operator's bare shell, or a missing one, goes through the restore decision.

## The restore decision

At `restore`, for each placed agent whose harness pane is `ABSENT`, or is at the operator's bare shell, the deck takes `before` and `live`.

`live` is the account's newest record once the deck has waited one poll (`STATE_POLL_MS` plus a margin, 5 s) for the changes the restart caused, and only when that record is fresh (within two heartbeats). The control agent posts on every change and on a ten-minute heartbeat, so a record from before the restore is current when nothing has changed since. With no fresh record (the host is still starting, or the account's control agent has been down for two heartbeats), the deck waits up to `RESTORE_WAIT_S` for one, then decides `IDLE`. An unknown `live` never leads to `--resume`. A control agent that died within the last two heartbeats leaves a record that looks fresh and may be wrong; there `fabric-resume`'s refusal, which reads the account's own session state rather than the stream, is what stops a second session.

- **`live` ≥ 1:** `ELSEWHERE`. The session survived (the deck or herdr restarted, not the host, or it runs in another terminal). The harness pane comes back as a plain `moveto` shell, never `--wait`: Enter must not start a second session.
- **`live` = 0, `before` had a session:** `STARTING`, the pane armed `--resume`. It was running and died with the restart, so it comes back. A stale `before` counts: a host restart is exactly when records go stale.
- **`live` = 0, `before` had none, or no fresh record:** `IDLE`, the pane armed `--wait`.

The shell and status panes always come back live (`moveto <account>`, `moveto <account> --watch`).

`before` is read only at `restore`, and written as the signals table says. A fall settles only on a herdr request answered by the same server instance at least `SETTLE_S` after it, so when herdr's server stops or restarts, no fall settles, whatever order the deck sees the harness end, `session-down`, the panes go and the socket fail, and however late it notices: the evidence that a session ran survives to the reconnect. A person who closes a running harness pane, or exits the session, leaves herdr up: the deck's first request to the same server at least `SETTLE_S` later settles the fall, and the next `restore` does not bring that session back.

Three limits, stated rather than solved:
- a person who ends a session within `SETTLE_S` plus one herdr request interval (2 s) of herdr being lost has it resumed at the next restore;
- at a host shutdown, harnesses stopped more than `SETTLE_S` before herdr settle as ended and are not resumed after boot;
- a person who ends a session, then the deck stops within `SETTLE_S` plus one request interval, and herdr's server restarts before the deck starts again: the pending fall never settles, and that session is resumed.

A deck that outlives herdr's server sees its panes go, then reconnects, or meets a new instance: either is a `restore`.

## What must hold whatever the deck does (fabric side)

Not yet built: python-dev builds `moveto --wait`, `moveto --watch` and the refusal below, in its activation PR. Until they are on main, the deck builds against stand-ins and arms no pane with them.

- **No second session.** This is required before the deck arms any pane `--wait` or `--resume`: the deck cannot re-arm a pane whose moveto runs, so an Enter in an `ELSEWHERE` pane reaches `fabric-resume`. `fabric-resume` refuses to start any session, resumed or fresh, while any session is alive on the account, and says which. Alive is read from the account's own session state as `runtime/control/sessions.mjs` counts it (a recorded pid alive with its start time), never from the stream. It is any session, not only the binding's: the binding names the last session started, and a session from another terminal may be older.

  A session enters that state only when it has started, so a check alone leaves a window in which two activations both pass. `fabric-resume` therefore takes an exclusive, non-blocking lock of the account's (`<state>/resume.lock`) before it checks, and hands the open lock to the launcher it execs: an `flock` on a descriptor marked inheritable before the exec, which the launcher holds for its own life (its restart wait and any session it relaunches included) and never passes to the harness; the kernel releases it when the launcher exits. `--print` takes no lock. A `--resume` refused because the lock is held (the launcher in its restart wait) ends that moveto with `live` = 0, so the tab shows `FAILED` for the moment; the relaunched session's `session-up` then moves it to `ELSEWHERE` (the `IDLE`, `FAILED` row), and the session is not lost. A second `fabric-resume` finds the lock held and refuses, naming the holder's pid. With both, a deck mistake or Enter pressed in two panes never starts a duplicate through `fabric-resume`. A person who launches by hand in the account's shell bypasses both, by choice (`ELSEWHERE` → `RUNNING`).
- **One Enter, one activation.** moveto `--wait` reads one line, then does exactly `--resume`. End of input gives a plain shell, said.
- **The mode stays readable.** moveto's hand-off keeps the mode as the last argument of `sudo … enter`, so the deck can read it from the foreground's argv.
- **Nothing types into an account.** The deck starts a fixed moveto command (`--wait`, `--resume`, `--watch`, plain) only in its own bare shell, never while moveto runs (re-arm, above). No pane receives a person's text from the deck.

## Open questions

- **A harness pane closed by hand:** `ABSENT` until the next restore, or re-created dormant on the deck's next pass? The default is "until restore", as with the other panes: the deck does not fight a layout a person chose.
- **`FAILED`:** when moveto ended, the pane is re-armed `--wait`, so one Enter retries; after a timeout it holds the account's shell. The deck never retries on its own: an automatic retry would hide a launcher that keeps failing.
