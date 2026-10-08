# Fleet Deck: the states of an agent's tab

The deck's behaviour, as one state machine per agent's **harness pane**. Every state is defined by what the deck can observe, never by a guess. Every event names its source. Every transition names the deck's action.

This note is the contract for:
- the deck (herdr, rust-ui-dev);
- `moveto`'s modes and `fabric-resume` (agent-fabric, python-dev).

`session-recovery.md` is the plan this formalises; where the two differ, this note is right.

## What the deck observes

| signal | source | what it says |
|---|---|---|
| **pane** | herdr: the tab, its panes, each pane's process alive or exited | whether the harness pane exists and runs something |
| **mode** | the deck itself: the fixed command it started the pane with (`--wait`, `--resume`, or a plain `moveto`) | what the pane was asked to do; the deck never reads the screen |
| **live** | the state stream, the account's newest record: `sessions[]` | how many sessions are alive on the account, wherever they run, each `working`, `idle` or `blocked` |
| **record age** | the same record's `ts` | fresh (within two heartbeats, 20 min) or stale |
| **before** | the account's newest record from before the deck's restore (the restore snapshot) | whether a session was alive when the deck or the host went down |
| **resumable** | the record's `last_session` and `resumable` | whether `fabric-resume` will resume or start fresh |

**`live` counts sessions on the account, not in the pane.** A session started from another terminal shows in `live` while the deck's harness pane holds no session. The machine therefore keeps "a session runs here" and "a session runs on the account" apart (`ELSEWHERE`).

## States of the harness pane

| state | defined as | the deck shows |
|---|---|---|
| `ABSENT` | no tab for a placed agent | (nothing; it is created) |
| `DORMANT` | pane alive in mode `--wait`, `live` = 0 | dormant |
| `STARTING` | pane alive in mode `--resume` (or `--wait` after Enter), `live` = 0, for less than `RESTORE_WAIT_S` (120 s) | restoring |
| `RUNNING(s)` | pane alive in a harness mode, `live` ≥ 1, record fresh; `s` is the state that most wants a person (blocked, then working, then idle) | resumed or fresh, then `s` |
| `ELSEWHERE` | `live` ≥ 1, but the deck's harness pane is `DORMANT`, or exited, or was never started | running elsewhere |
| `SHELL` | the harness pane alive with no session: the session ended and the account's shell remains (`live` = 0 after `RUNNING`) | shell |
| `FAILED` | `STARTING` for more than `RESTORE_WAIT_S`, or the pane's process exited non-zero before any session appeared | failed (the pane's last line says why) |
| `STALE` | the account's newest record is older than two heartbeats | stale (overrides the others in the display, never in the decisions) |

**A plain shell is never a running agent.** An open moveto shell, with or without a person typing in it, is `SHELL` or `DORMANT`, never `RUNNING`.

## Events

| event | source |
|---|---|
| `enter` | a person presses Enter in a `DORMANT` pane (moveto `--wait` reads it, not the deck) |
| `session-up` | the stream: `live` goes from 0 to ≥ 1 |
| `session-down` | the stream: `live` goes from ≥ 1 to 0 |
| `pane-exit` | herdr: the harness pane's process exited |
| `pane-closed` | herdr: a person closed the pane or the tab |
| `timeout` | `RESTORE_WAIT_S` elapsed in `STARTING` |
| `restore` | the deck starts: after a deck, herdr or host restart |
| `stale` / `fresh` | the record's age crosses two heartbeats, either way |

## Transitions

| from | event | to | the deck does |
|---|---|---|---|
| `ABSENT` | `restore` | see **The restore decision** | create the tab: harness, shell and status panes |
| `DORMANT` | `enter` | `STARTING` | nothing: moveto `--wait` runs `--resume` itself |
| `DORMANT` | `session-up` | `ELSEWHERE` | nothing; it must not start a second session |
| `STARTING` | `session-up` | `RUNNING` | report the state to the panel |
| `STARTING` | `timeout`, or `pane-exit` non-zero | `FAILED` | report failed; never retry by itself |
| `RUNNING` | `session-down` with the pane alive | `SHELL` | report shell |
| `RUNNING` | `pane-exit` | `SHELL` if `live` = 0, `ELSEWHERE` if not | re-arm the pane `--wait`, so it returns to `DORMANT` and stops there (only a restore resumes) |
| `SHELL` | the person relaunches in the pane, then `session-up` | `RUNNING` | report it |
| `SHELL` | `pane-exit` | `DORMANT` | re-arm the pane with `--wait` |
| `ELSEWHERE` | `session-down` | `DORMANT` | nothing; it is already waiting |
| `FAILED` | `enter` (a new `--wait` the person asks for) | `STARTING` | re-arm with `--wait` only on the person's action |
| any | `pane-closed` (harness) | `ABSENT` until the next `restore` | nothing: the person chose the layout |
| shell or status pane | `pane-closed` | (no change) | re-created only at the next `restore` |

## The restore decision

At `restore`, for each placed agent, the deck takes `before` (the snapshot) and `live` (a record no older than the restore itself, waited for up to one poll):
- **`live` ≥ 1:** `ELSEWHERE`. The session survived (the deck or herdr restarted, not the host, or it runs in another terminal). The harness pane comes back `--wait`, and no second session is started.
- **`live` = 0, `before` had a session:** `STARTING` in mode `--resume`. It was running and died with the restart, so it comes back. A stale `before` counts: a host restart is exactly when records go stale.
- **`live` = 0, `before` had none, or no record at all:** `DORMANT`, mode `--wait`.

The shell and status panes always come back live (`moveto <account>`, `moveto <account> --watch`).

## What must hold whatever the deck does (fabric side)

- **No second session.** `fabric-resume` refuses to resume when the binding's session is alive on the account (`sessions[]` lists it), and says so. A deck mistake, or Enter pressed in two panes, never starts a duplicate.
- **One Enter, one activation.** moveto `--wait` reads one line, then does exactly `--resume`. End of input gives a plain shell, said.
- **Nothing types into an account.** The deck acts only by starting a pane with a fixed mode (`--wait`, `--resume`, `--watch`, plain). No pane receives a person's text from the deck.

## Open questions

- **A harness pane closed by hand:** `ABSENT` until the next restore, or re-created dormant on the deck's next pass? The default is "until restore", as with the other panes: the deck does not fight a layout a person chose.
- **`FAILED`:** stays until a person acts. An automatic retry would hide a launcher that keeps failing.
