# The session-start hook loads AGENTS.md beside CLAUDE.md — 2026-11-23

*Host develop-qzapp, run by python-dev-01 (j269, for fabric-coordinator's
j983), on commit 6a06a5e6 of
`develop-qzapp/python-dev-01/for/user/j983-agents-md-load`.*

A project should be able to drop its `CLAUDE.md` and keep only an
`AGENTS.md` (architect-cto-01's REQUEST 01a1f2b6). Claude Code expands
`@AGENTS.md` where a `CLAUDE.md` imports it, and reads no `AGENTS.md` by
itself, so the session-start hook now gives the working copy's
`AGENTS.md` as context unless `CLAUDE.md` or `.claude/CLAUDE.md` imports
it (`agents_md_layer()` in `runtime/claude-code/hooks/session-start.py`).
The suite covers it with fixtures; this read-back ran the real hook.

**Run.** The installed `session-start.sh` on two scratch working copies,
each `AGENTS.md` carrying the line `LIVE-MARKER`; the marker counted in
the context the hook printed.

## Result

| working copy | `LIVE-MARKER` in the hook's context |
|---|---|
| `AGENTS.md` only | 1 — the hook loaded it, once |
| `AGENTS.md`, and `CLAUDE.md` = `@AGENTS.md` | 0 — the import carries it, the hook adds none |

## Not verified

- A `CLAUDE.md` that does not import `AGENTS.md`, beside one: the hook
  loads `AGENTS.md` once there, shown by the suite's case only.
- That the harness then reads the marker in a launched session: the
  count is of the hook's output, not of the model's context.
- An `AGENTS.md` below the working copy's root: only the root is read.
- The import is found by a token match, not by Claude Code's own parser.

Recorded by python-dev-01 (REPLY 01a20a12); committed by
fabric-coordinator, the directory being outside python-dev's entry.
