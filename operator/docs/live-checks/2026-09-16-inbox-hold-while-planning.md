# The inbox hold, read back — 2026-09-16

The design in `docs/inbox-hold-while-planning.md` rests on three
harness facts and one end-to-end behaviour. Each was measured on
`develop-qzapp`, Claude Code 2.1.273, as login `user`.

## The harness facts (headless probes, a hook that dumps its input)

1. **Every hook event carries `permission_mode`**, except SessionStart.
   A session started with `--permission-mode plan` delivered
   `UserPromptSubmit` and `PreToolUse` events with `permission_mode:
   "plan"`; the SessionStart event had only `hook_event_name` and
   `source`. So the marker follows the mode from the first prompt, and
   the session-start drain is not held (it runs before any planning).
2. **Hooks get `CLAUDE_PID` and `CLAUDE_CODE_SESSION_ID` in their
   environment, and their parent process is the harness itself**
   (`PPID` → `comm=claude`). The marker names that pid; liveness is
   `kill -0`.
3. **The session itself sends `agent_id: null`**, not an absent key.
   (That a subagent's event carries a non-null `agent_id` is what the
   subagent clone guard already relies on, read back 2026-09-14.)
   The first version of the hook split its four fields on whitespace
   and slid `session_id` into `agent_id`, taking every session for a
   subagent and writing nothing — the unit test had passed because its
   payloads carried no `session_id`. Fixed to one field per line, and
   the test now sends the harness's shape (`session_id` present,
   `agent_id: null`). This is the defect the read-back existed to find.

## End to end (a watch in this session, a plan session under the same login)

The watch (`inbox.mjs --follow` under a Monitor) was armed in this
interactive session. A second, headless session under the same login
was started with `--permission-mode plan` and the bootstrapped
workspace settings (the hook wired on `PreToolUse`, `UserPromptSubmit`
and `SessionEnd`), and given six Read calls to make. Meanwhile a
message addressed to `develop-qzapp/user` was sent through `send.mjs`.

| UTC | observed |
|---|---|
| 11:42:39 | first prompt: the marker written (then at `/tmp/agent-fabric-hold-1000/user.json`; since the review, one file per session under `~/.cache/agent-fabric/hold/`), naming the plan session and pid 1453504; `--held` says held |
| 11:42:41 | probe message accepted by the relay as seq 414 |
| 11:42:50 | `--held` still held; the watch's stderr says `inbox held — the session is planning`; nothing on its stdout |
| 11:43:02 | plan session replied "done" and exited; SessionEnd cleared the marker; `--held` says not held |
| 11:43:03 | watch stderr `hold released; polling again`; seq 414 delivered to this session as one notification |

So: a message sent while the account plans is not consumed, not
printed and not notified until the planning session ends, then lands
whole, once, with no loss (the relay re-showed it on the first poll
after release).

## What it decides

- The hold works at the address, across sessions of the login, which
  is the semantics the cursor already has.
- `SessionEnd` is a reliable release for a session that ends in plan
  mode; approval of a plan releases at the next tool call or prompt of
  that session (a `permission_mode` other than `plan`), which was not
  exercised here because a headless session cannot approve a plan.
- The unit tests must send the harness's real payload shape; a hand-made
  payload that omits a field the harness always sends is how this
  defect got past the suite.

## Not read back

- **Release by plan approval in an interactive session** (the
  `ExitPlanMode` → next-event path). The mechanism is the same field on
  the same events; the timing of the first post-approval event is the
  only unmeasured thing.
- **A session started inside a clone.** Such a session takes its hooks
  from the clone's own `.claude/settings.json`, not the workspace's
  (`runtime/openrouter/launch` records this; the first blind review of
  this change caught the note claiming otherwise). The workspace
  template wires the hook; each managed project's settings must wire it
  too (`projects/gzapp/integration/gzcoord/INSTALL.md` step 2), and
  until it does the hold reaches only workspace-started sessions. Not
  measured in a clone.
- **The 55 s slice cut.** The unit test covers the abort; live, the hold
  began before the watch's slice in flight returned, so the cut was not
  observed separately from the ordinary hold.

## After the blind review (same day)

The review of the two commits found the marker's home wrong (a per-uid
name under `/tmp` that another login could create first and own — P1),
one file per login releasing a sibling session's hold (P2), the
clone-started session not covered (P2, above), the hook and the watch
disagreeing on liveness for a pid this login cannot signal (P3), and a
page fetched in the same second as the hold being delivered (P3). All
five are fixed in the commit that follows: markers live under the
login's home, one per session, naming the harness pid and its start
time; the directory must be the login's, mode 700, not a symlink; a pid
that answers EPERM is nobody's harness on both sides; the slice's page
is dropped unread when the hold began while it was in flight; and the
guard's tick is cut when the slice ends, so a delivery waits for no
tick. The end-to-end run was repeated with the reworked mechanism:
marker `~/.cache/agent-fabric/hold/1611500.json` (directory `user 700`)
written at 12:07:08 on the plan session's first prompt, carrying pid
and start time; probe seq 430 sent 12:07:09; still held 12:07:17;
session ended 12:07:30, marker swept, and the probe delivered to this
session's watch at once.

Two risks the review named stay open as risks: a permission mode
changed with the keyboard while the session is idle fires no hook, so
the hold begins or ends at the session's next prompt; and a pid reused
by a process of this login with the same start tick is not
distinguishable from the harness (start times are clock ticks since
boot; the odds are negligible).
