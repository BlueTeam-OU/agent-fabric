# ADR-022 — The session lifecycle: auto mode, the watch armed at launch, the inbox held while planning and visible to senders

**Date:** 2026-09-13
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #52 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** runtime/claude-code/user-settings.py (`permissions.defaultMode`); runtime/openrouter/launch (the opening prompt, the restart marker); bin/fabric-fresh; bin/fabric-branches and policies/branch-hygiene/SKILL.md; runtime/claude-code/workspace/settings.json and each managed project's `.claude/settings.json` (the hook wiring); runtime/claude-code/hooks/session-start.py (the watch check), runtime/claude-code/hooks/plan-hold.sh; communication/gzcoord/scripts/inbox.mjs and send.mjs; runtime/control/ops.mjs, runtime/control/presence.mjs, runtime/control/ctl.mjs (presence); communication/gzcoord/skills/gzcoord-receive/SKILL.md
**Pillar:** P3
**Evidence:** docs/live-checks/2026-09-16-inbox-hold-while-planning.md

## 1. Context and Problem

An agent's session is how it takes part in the team: it hears other
agents through its GZCoord inbox and acts through tools its permission
mode allows. Three gaps showed up in how a session starts and runs.

The inbox watch is a Monitor only the session itself can arm, and a
session acts only on a turn. A session left alone after a launch or a
resume had no watch and no sign of it: after their restarts on
2026-09-25 two roles' inboxes went quiet, and the skill that said to
re-arm was not reread by a resumed session. Eight accounts provisioned
by hand had no permission mode and asked for what the classifier would
allow. And a delivery that landed while a session was writing a plan
changed the plan's inputs without anyone deciding it should, so the
approval that followed judged a plan whose inputs had moved (2026-09-16);
once the hold existed, a sender could not tell a planning session from a
running one and waited on an answer that could not come.

## 2. Decision

**Every session watches its inbox from its first turn to its last**,
with one watch per session: `gzcoord-inbox --follow`
under a Monitor. The launcher opens every
interactive session it starts without a prompt of its own with one that
arms the watch, and the session-start hook says so, on start, resume and
after a compaction, whenever no watch runs for the session.

**Every session starts in auto mode**:
`user-settings.py` writes `permissions.defaultMode: "auto"` into each
login's user settings, beside the narrow allow rules for the fabric's
commands (ADR-008, ADR-009), which assume it.

**While a session plans, its inbox is held**:
nothing new lands in a plan. A hook marks the account held while the
session's permission mode is `plan`; the watch polls nothing while a
marker names a live harness of the login; the first poll after the plan
is approved delivers the whole planning span at once.

**The hold is visible to senders**: presence
reports `planning`, `fabric-ctl presence` shows it in place of
`running`, and `gzcoord-send` tells the sender — without refusing — that
the message waits in the relay and no answer comes before the plan is
approved.

## 3. Alternatives Considered

- **Leave arming to the start hook's instruction.** The first shape; a
  hook cannot start a Monitor, and its instruction waited for whatever
  prompt came first. The opening prompt makes the watch the session's
  first turn; the hook's line gives the exact call, at start and for a
  resume or compaction that lost the watch.
- **A shell loop, or `--wait` with a budget, as the watch.** Replaced by
  `--follow`: one process that prints only deliveries, re-armed only on
  a timed Monitor's expiry.
- **Pause notifications in the harness.** Not offered, and not needed: a
  delivery becomes a notification only because the watch prints it, so
  the hold lives in the fabric's own lane.
- **Hold on the `EnterPlanMode`/`ExitPlanMode` calls.** Rejected: a
  rejected plan stays in plan mode, and a plan entered by launch flag
  never calls the tool; the marker follows the event's `permission_mode`.
- **Refuse a send to a planning session.** Rejected: messages are
  advisory and late by nature; the sender is told, and the message
  waits.

## 4. Rationale

Agents coordinate among themselves (ADR-000, P3), which needs each of
them reachable from the moment it runs; a watch that depends on the model
remembering to start it is reachability by luck. A plan is bounded by an
approval, so holding deliveries until then costs a sender at most that
span, and saying so to the sender turns a silent wait into a known one.
Auto mode is what the fabric's allow rules were written for; without it
the same command asks on one account and not on another.

## 5. Binding Rules

1. An interactive launch through `runtime/openrouter/launch` that the
   caller gave no prompt of its own — no `-p`, no `--version`/`--help`,
   no positional word, no caller-written `--`, and no
   `AGENT_FABRIC_NO_OPENING` — ends its command line with `--` and an
   opening prompt that tells the session to arm its inbox watch exactly
   as the start hook's `NO INBOX WATCH` line gives it (the gzcoord-receive
   skill, where the context has none) and to re-arm at each expiry
   notice. The prompt names no command: it stays in the process's argv,
   where a kill by a pattern built from that command matched the session
   itself (A 2026-09-30).
2. The session-start hook, on start, resume and after a compaction,
   prints a `NO INBOX WATCH` line naming the Monitor call whenever no
   `gzcoord-inbox --follow` (or `inbox.mjs --follow`) runs under the
   session; the workspace settings also drain the inbox once at session
   start, which a hold does not stop.
3. One watch per session: the cursor is per address, and a second
   consumer steals deliveries from the first. The watch is run by the bare
   command name, never through an expansion (ADR-009 §5 rule 8).
4. Every login's user settings carry `permissions.defaultMode: "auto"`,
   written by `user-settings.py` on every bootstrap.
5. `plan-hold.sh`, wired on `PreToolUse` (no matcher), `UserPromptSubmit`
   and `SessionEnd`, writes `~/.cache/agent-fabric/hold/<pid>.json` —
   the harness pid, its start time from `/proc`, the session id — while
   the event's `permission_mode` is `plan`, and removes it otherwise; it
   ignores a subagent's event, writes nothing unless the directory is
   the login's, mode 700 and not a symlink, sweeps markers whose harness
   is gone or whose pid was reused, and writes nothing at all without
   `jq`.
6. `inbox.mjs --follow` polls nothing while any marker names a live
   harness of this login (a pid of another login is never a hold),
   checked before each slice, once a second during one and when it
   returns; nothing is acknowledged while held, so the relay re-shows
   it. Held and released are one line each on stderr, never stdout.
   Sending, the session-start drain and a deliberate `--wait` read are
   not held; `gzcoord-inbox --held` says whether the inbox is held and by
   which session.
7. The hold is per address: every planning session under a login holds
   with its own marker, and the account is released when the last leaves
   plan mode.
8. The control agent's `presence` reports `planning` when a session runs
   and the hold is on; `fabric-ctl presence` prints `planning` in place of
   `running`; `gzcoord-send` prints, without refusing, that the addressee
   is planning. A role is planning only when every running holder is.
9. A session started inside a managed project's working copy is held, and
   gets the start drain, only if that project's `.claude/settings.json`
   wires the same hooks as the workspace template.
10. An agent ends its own finished job with `fabric-fresh`: it writes a
    restart marker with `fresh` true and a one-line note, and stops its
    own session gracefully; the launcher relaunches with no `--resume`,
    the note in the new opening prompt. It is refused outside a launched
    session, where the launch carried its own prompt (the relaunch would
    replay it), and on a working copy with uncommitted changes, untracked
    files included, unless `--force`. It is used when a job has reached
    its artifact and nothing it still waits on needs the conversation;
    whether the next job belongs in this session is rule 12's
    (A 2026-09-28). `--job <id>` names the job the fresh session is for.
11. Each working copy's local branches are swept weekly with
    `fabric-branches --sweep`, after a plain fetch: the agent deletes on
    its own what is wholly on the remote's default branch (`origin/HEAD`,
    else the project registry's; unknown, it refuses), and worktrees at
    0 with no changes, no ignored files and no lock, never the one it
    runs in; a branch with commits off it is kept and brought to the
    person. Local only: no remote branch is deleted or pushed. The
    session-start hook says when a working copy's last sweep is older
    than seven days; nothing runs on a timer (A 2026-09-28).
12. The next job decides whether the session continues (ADR-037). At a
    job's end, `fabric-jobs next` compares the next job with the one that
    ended. The same project, working copy and topic continue in this
    session. Any difference is a fresh session: the agent runs
    `fabric-fresh --job <id>`, and the launcher relaunches in that job's
    working copy with the job in its opening prompt. A working copy
    that is gone or has uncommitted changes is refused by the launcher,
    which starts in the old directory and says why. The command decides
    and the agent confirms; nothing restarts a session on its own
    (A 2026-09-28).

## 6. Consequences

- A resumed session is told it has no watch; a relaunched one arms it on
  its first turn. The Monitor tool is timed (the pinned Claude Code has
  no `persistent` field), so re-arming at the expiry notice stays the
  session's job (`gzcoord-receive` §1).
- After a plan is approved the planning span's deliveries arrive
  together, and the session reads them before acting: the tree may have
  moved.

## 7. Future Evolution

- Not read back (the live check's own list): release by plan approval
  in an interactive session, a session started inside a clone, and the
  cut of a long-poll slice in flight. `SessionEnd` was measured as a
  reliable release.
- Rule 9 is each project's to meet. Of the checkouts on this host at the
  last count, gzapp, gzapi.ge and gzapi.brand wire the hold and the
  start drain in their `.claude/settings.json`; interweave and
  gzapp.decks do not, so a session started inside those is neither held
  nor drained at start.
- Two risks stay open: a pid reused by this login's process with the same
  start tick reads as the harness, and a mode changed by keyboard while
  idle moves the hold only at the next event.

## 8. Decision Status

Accepted and in force: the watch from the first turn; the hold; the
opening prompt, auto mode and the sender's view. The note that recorded
the hold is now a stub pointing here.

## References

- `runtime/openrouter/launch` (THE WATCH STARTS WITH THE SESSION),
  `tests/test_launch_cli.py`.
- `runtime/claude-code/hooks/session-start.py` (`WATCH_MISSING`),
  `tests/test_session_start.py`; `runtime/claude-code/hooks/plan-hold.sh`,
  `runtime/claude-code/hooks/test_plan-hold.sh`;
  `runtime/claude-code/workspace/settings.json`.
- `communication/gzcoord/scripts/inbox.mjs` (`holdStatus`),
  `communication/gzcoord/scripts/send.mjs`, `communication/gzcoord/tests/`.
- `runtime/control/ops.mjs` (`presence`), `runtime/control/presence.mjs`,
  `runtime/control/ctl.mjs`; ADR-030.
- `runtime/claude-code/user-settings.py`.
- `communication/gzcoord/skills/gzcoord-receive/SKILL.md` §1.
- ADR-008 (user settings), ADR-009 (commands by name), ADR-000 (P3).

## Amendments

The body above reads current; each change's full note is in [history/ADR-022-amendments.md](history/ADR-022-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-09-28 | An agent ends its own job with a fresh session | §5 rule 10: `fabric-fresh` and the launcher's fresh relaunch |
| 2026-09-28 | Local branches are swept weekly | §5 rule 11: `fabric-branches --sweep`, the weekly nudge at session start |
| 2026-09-28 | The next job decides whether the session continues | §5 rule 12: `fabric-jobs next` and `fabric-fresh --job`; rule 10 points to it |
| 2026-09-30 | The opening prompt names no command | §5 rule 1, §3: the prompt defers the exact Monitor call to the hook's line |
