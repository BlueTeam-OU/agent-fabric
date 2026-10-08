# Fleet Deck: bringing the agents' sessions back

Fleet Deck is the terminal workspace (herdr, gzapi-org's fork) in which
the owner watches every agent's tab and re-enters one. This note is the
plan for its first milestone: when herdr's server stops, every pane
process dies, and the tabs come back as bare shells; the deck must bring
each agent that was running back into its harness, resumed, and leave
the others one key from activation (the owner, 2026-10-08). architect-cto
drafted it with rust-ui-dev's measurement (2026-10-07); fabric-coordinator
took it with the changes below. herdr's side is rust-ui-dev's; the
control plane's is fabric-coordinator's.

## What holds today

- Stopping herdr's server kills every pane process; layout and labels
  come back as fresh shells, and nothing re-enters an account.
- herdr's own agent restore needs a pane process to report a session
  over herdr's socket, which is the operator's (0600) and refuses pane
  processes (`server.socket_access = outside_panes`). An agent entered
  with `moveto` must not report through it: the one-way rule of ADR-010
  rule 12 and the socket's ownership are the same fence.
- The control plane already knows what herdr lacks: each account's
  binding (its last session id and working copy), the state stream
  (`fabric-ctl states --follow --json`, ADR-029 rule 16), and a launcher
  that relaunches a stopped session with `--resume`.

## The decisions

1. **The control plane owns which session belongs in which tab**, by
   account. herdr keeps the layout only (tab, label = account, cwd); the
   deck keeps no session ids and rebuilds the tab-to-account mapping
   from the labels.
2. **A session is brought back by the account's own launcher.** The
   deck runs `moveto <account> --resume` in the tab: moveto enters the
   account as always and runs `fabric-resume`, which resumes the
   binding's last session in the directory its transcript names, or
   starts fresh and says so. When that session ends, the account's shell
   follows. The deck never runs `claude --resume` itself; herdr never
   learns a fleet session.
3. **The contract.** Inputs to the deck: `moveto --list` (the accounts)
   and the state stream, whose record carries, per account, its live
   sessions with state and since when, the binding's role and project,
   and `last_session` with `resumable` (ADR-029 rule 16, amended
   2026-10-08). No path is in the record. Outputs from the deck: none
   into the control plane; it acts through herdr (tab create,
   `pane run "moveto <account> --resume"`) and reads. A record older than
   two heartbeats reads as stale, never as running.
4. **The deck runs on a human login** (ADR-044), as a person, outside
   any pane: herdr's server and socket are that login's, `moveto` uses
   its sudo grant, and it reads the stream with its own relay
   credential. It holds no signing key for the control plane. An agent
   never runs the deck.
5. **What comes back, and how it is activated.** A tab per agent,
   labelled with its account, with three panes, each opened by moveto
   as the account with a fixed mode, so no pane runs a person's text:
   - **harness** (the largest): after a restart, `moveto <account>
     --resume` when the account's newest state record from before the
     restart listed a live session (working, idle or blocked), however
     stale that record has become; otherwise `moveto <account> --wait`,
     which shows one line and does `--resume` on Enter. An open shell
     with no session is not a running agent: it comes back dormant. The
     deck never activates a dormant harness itself.
   - **shell**: `moveto <account>`, a plain shell as the account.
   - **status**: `moveto <account> --watch`, the read-only `fabric-watch`
     (the account's status, jobs and open pull requests).

   A first activation with no launch on record takes the provider of
   `routing/profiles.json` `launch_provider` for the account, its role or
   the defaults.
6. **What the deck shows** per tab, in the deck's own output only (a
   tab's label stays the bare account: the label is the mapping):
   - dormant: the harness waits for Enter;
   - restoring: entered, no state yet;
   - resumed: the stream reports a live session (its `sessions[]` state
     working, idle or blocked) for the account;
   - fresh: fabric-resume found nothing to resume, and said so;
   - failed: moveto or fabric-resume exited with no session reported, or
     restoring lasted longer than `RESTORE_WAIT_S` (120 s, the upgrade's
     stop budget plus a launcher start; a deck constant the owner may
     change). The pane's last line says why;
   - stale: the account has no record in the stream, or its newest is
     older than two heartbeats (the stream posts on every change and
     every ten minutes, so age alone is meaningful only past that).

   The record's two fields are `last_session` (a string, the binding's
   session id) and `resumable` (a boolean, true when that session's
   transcript is on the account). No working copy or other path is in the
   record: the deck re-enters with `moveto <account> --resume`, and
   fabric-resume reads the directory from the transcript and prints
   resume or fresh. With the fields absent (an older agentd), the deck
   re-enters regardless and fabric-resume decides.

## Milestone 1

- **fabric-coordinator** (agent-fabric): `fabric-resume`, `moveto --resume`
  (its installed copy is refreshed by the owner with
  `runtime/provisioning/moveto/install.sh`), the state record's
  `last_session` and `resumable`, the human identity kind (ADR-044) and
  provisioning a human login.
- **python-dev** (agent-fabric): `moveto --wait` and `--watch`, and
  `fabric-watch`; fabric-coordinator supplies the profile's
  `launch_provider` and `fabric-resume`'s use of it.
- **rust-ui-dev** (herdr): the deck's recovery loop (compare tabs with
  `moveto --list` and the stream; give every account its three-pane tab;
  restore the harness of each account that had a live session and leave
  the rest dormant; show the six states), and herd.py's retirement into
  the deck.

Acceptance: stop and start herdr's server with some account tabs
holding a running session and some only a shell. The deck brings each
running one back into its account with its session resumed (the stream
shows the same `last_session` as before the stop), says fresh where
there was no transcript and failed where the launcher failed, leaves
every other harness dormant until Enter, opens every shell and status
pane, and leaves every other workspace untouched. Measured on an isolated server first, then on
develop-qzapp by the owner's run.

## Milestone 2, later

herdr's own status for the fleet's tabs, reported by the deck from the
stream as the human login (`pane report-agent`), which the socket's
fence allows, so a tab no longer reads "agent status unknown".
