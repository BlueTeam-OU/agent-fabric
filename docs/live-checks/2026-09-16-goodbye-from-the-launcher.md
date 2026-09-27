# Live check 2026-09-16 — GOODBYE is the launcher's, after the session returns

> The launcher's HELLO and GOODBYE were retired on 2026-09-25: presence is asked of the control plane (`docs/adr/ADR-030-presence-replaces-hello-and-goodbye.md`); the measurement stands.

Host `develop-qzapp`, agent `user`, role `fabric-coordinator`, Claude Code
`2.1.272`, `runtime/openrouter/launch --provider anthropic`. Read back on
the relay through this session's own inbox watch (`inbox.mjs --follow`),
which prints every message addressed to the address, HELLO and GOODBYE
being broadcasts.

## Why the launcher and not a harness hook

The harness has a `SessionEnd` hook event (`reason`: `prompt_input_exit`,
`logout`, `clear`, `other`), but it fires on the exit paths the harness
chooses to run it on, and a double Ctrl-C, a crash or a `kill` of the
process are the cases a departure notice is for. The launcher already
sends the HELLO just before the session; the owner's rule (2026-09-16):
the same script sends the GOODBYE, after the session returns, whatever
ended it. So the launcher no longer `exec`s the session — it runs it as
a child with the terminal as stdin (`<&0`; an `&` job in a script would
otherwise get `/dev/null`), ignores SIGINT itself so Ctrl-C is the
session's (one interrupts a turn, two end it), forwards SIGTERM and
SIGHUP to the child, waits, sends the GOODBYE with how the session
ended, and exits with the child's status.

## 1. Headless

`launch -p 'Reply with exactly: ok'` — HELLO seq 348 at 03:28:07Z,
`ok`, GOODBYE seq 349 at 03:28:15Z with `NOTES: session ended`, launcher
exit 0.

## 2. Interactive, `/exit`

Through a pty (`script -qfec`), `/exit` typed after 25 s — HELLO seq 350,
GOODBYE seq 352 with `session ended with status 1`: the pty's stdin
closed under the session, and the launcher reported that status rather
than a clean 0. The note says how the session ended; it does not
pretend.

## 3. Interactive, double Ctrl-C

Same pty, `^C ^C` 0.4 s apart after 25 s — HELLO seq 353, GOODBYE seq
354. The launcher, which ignores SIGINT while the child runs, was still
there to send it; the session, which does not, ended.

## 4. In the sandbox (`runtime/openrouter/test_launch.sh`)

With a recording stub in place of `tools/fabric/announce.py`: exactly
one HELLO and one GOODBYE per launch, in that order; a session exiting 3
makes the launcher exit 3 and the GOODBYE say `status 3`; a session
ended by SIGTERM makes the launcher exit 143 and the GOODBYE say
`signal 15`.

## What this decides

- `HELLO` and `GOODBYE` are both the launcher's; no hook, no in-session
  step, nothing an account does by hand. A `GOODBYE` on the channel
  means the session's process is gone; its NOTES say how.
- Not covered, by the nature of the thing: a SIGKILL of the launcher
  itself, or the host going down — SPEC §GOODBYE already says peers
  must not rely on receiving one.
- A running session launched before this change was `exec`'d and has no
  parent waiting: it sends no GOODBYE when it ends. Its next launch does.
