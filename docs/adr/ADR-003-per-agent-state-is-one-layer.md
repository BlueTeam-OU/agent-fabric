# ADR-003 — Per-agent state is one layer

**Date:** 2026-09-16
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #51 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** fabric-coordinator, on the review of 2026-09-16 (items 1, 2, 5, 6)
**Scope:** everything under `${XDG_STATE_HOME:-~/.local/state}/agent-fabric/agents/<login>/`; runtime/identity.py; tools/fabric/role.py, runtime/claude-code/hooks/session-start.py, runtime/provisioning/rename_history.py and rename-working-copy.sh
**Pillar:** P1

## 1. Context and Problem

Runtime state — the role bound, the working copy, the session, the role
history, the agent's own model choices — lives outside the repository,
per login (ADR-002). Before 2026-09-16 `runtime/identity.py` owned the
binding's *shape* (`read_binding` refused another agent's record,
`write_binding` stamped agent and host) but not its *writes*. Four places
rewrote per-agent state their own way: the role activator (binding and
`role-history.jsonl`), the session-start hook (session id and working
copy on every start and resume), `rename-working-copy.sh` (binding,
transcripts, `~/.claude.json`, `history.jsonl`, rewritten in place from a
shell heredoc) and the launcher's stamps.

None held a lock: a hook firing while `fabric-role` wrote lost one of the
two updates, and a kill mid-rewrite left a truncated file. The host was
recorded but never checked, so a home shared between two machines carried
a binding from one to the other. A history directory already present
under a rename's new key was overwritten file by file (review,
2026-09-16, items 1, 2, 5, 6).

## 2. Decision

Every write to `agents/<login>/` from Python goes through
`runtime/identity.py`, and only through it:

- `atomic_write(path, data)` — a temporary beside the target, fsync,
  `os.replace`; the previous file is whole at every instant, and a
  temporary left by a crash is removed by the next write;
- `agent_lock(agent)` — a re-entrant `flock` on `agents/<login>/.lock`,
  held by every read-modify-write of per-agent state, across processes;
- `update_binding(mutate, agent)` and `append_history(record, agent)` —
  the two operations callers need, built on both.

The one writer that cannot import it — the account's control agent, in
Node, which writes `restart.json` for a fleet upgrade
(`runtime/control/upgrade.mjs`) and its ledger of signed actions seen,
`actions-seen.json` (`runtime/control/agentd.mjs`) — writes in the same
shape, a temporary beside the target, then a rename; it takes no
`agent_lock`, and what serializes it is that one control agent runs per
account. The launcher is the other party to `restart.json`: after its
session stopped it polls the marker until the control agent records the
upgrade's outcome, or until `AGENT_FABRIC_RESTART_WAIT_S` (600 s by
default) passes, then removes it; a marker the control agent writes
after that is older than the next launch, which discards it. Both sides replace the whole file or
remove it, never edit it in place. The session writes the marker
too when it ends its own finished job (`bin/fabric-fresh`, ADR-022),
through `identity.atomic_write`; the launcher reads a fresh marker at
once and waits on nothing.

The second class is a self-contained transactional store: a database
that owns its own atomicity and locking, which `atomic_write` and
`agent_lock` would only duplicate or defeat. The agent's episodic
journal, `agents/<login>/episodic.db` (ADR-041), is the one such store:
SQLite in WAL mode, written only by `tools/fabric/episodic.py`, every
write a short transaction (`BEGIN IMMEDIATE`, a 5 s busy timeout), the
directory 0700 and the files 0600, and its own schema version migrated
in the opening transaction. Its path comes from
`identity.agent_state_dir()`, as every other file's does.

A binding is per (agent, host). A working-copy rename merges history,
never overwrites it.

## 3. Alternatives Considered

- **Each writer keeps its own code, with care.** That was the state
  before; four writers with no shared lock lost updates and truncated
  files, which is why the layer exists.
- **A binding valid on any host sharing the home.** Rejected: two
  instances of one login would write over each other's binding. The
  identity is still the login; what it *holds* is bound where it was
  bound.

## 4. Rationale

The binding is what `fabric-status`, the launcher and the hooks trust
about a running agent. One writer with an atomic replace and one lock
turns every race and crash in §1 into a non-event, and gives the next
state file an obvious place to get its writer.

## 5. Binding Rules

1. No caller opens a file under `agents/<login>/` for writing; it imports
   `identity` and calls `atomic_write`, `update_binding`,
   `append_history` or `update_jobs`, the job list's writer (ADR-037)
   (A 2026-09-28). A new state file gets its writer added to
   `runtime/identity.py`, not a rewrite in place elsewhere. The Node
   control agent is the named exception (§2), and writes only by
   temporary and rename. A self-contained transactional store (§2) is
   the other: `episodic.db`, written only by `tools/fabric/episodic.py`
   through its own transactions (A 2026-10-05). Two append-only GZCoord
   logs are the third: `journal-bypass.jsonl` (ADR-041 rule 10), appended
   by `tools/fabric/gzcoord/bypass.py` under `agent_lock` with
   `O_NOFOLLOW`, mode 0600, one write and an fsync per line, and
   `gzcoord-sent.jsonl`, the send ledger, which does not yet hold
   `agent_lock` when it trims (a known gap, to close).
2. Every read-modify-write of per-agent state holds `agent_lock`, except
   the Node control agent's own files (§2), which only it writes and the
   launcher only consumes; `restart.json` has a second writer,
   `bin/fabric-fresh`, which replaces it whole through `atomic_write`
   (A 2026-09-28).
3. `read_binding` refuses a record that names another agent or whose
   `host` is not this machine's, with the same wording, and says how to
   bind here. A move between hosts is a rebind there.
4. A rename (`runtime/provisioning/rename_history.py`, run as the account)
   plans the merge before moving anything: same name and bytes, one copy;
   same name and different bytes, both kept, the incoming one suffixed
   `.from-<old key>`; a directory on both sides is refused before the
   first move. Every Claude Code file it touches is written with
   `atomic_write`.
5. The session-start hook stays non-blocking: a refused binding (another
   agent's, another host's) reaches the session as context, not as a
   failed start.

## 6. Consequences

- `tests/test_identity.py` proves the lock with four processes racing one
  counter and one history file; `tests/test_rename_history.py` the merge.
- A shared home no longer carries a role between hosts; the cost is a
  rebind on each host an account is used from.

## 7. Future Evolution

None stated. A new per-agent file is the case that exercises rule 1.

## 8. Decision Status

Accepted and in force.

## References

- `runtime/identity.py` (module docstring, `atomic_write`, `agent_lock`,
  `update_binding`, `append_history`, `read_binding`).
- `tools/fabric/role.py`, `runtime/claude-code/hooks/session-start.py`,
  `runtime/provisioning/rename_history.py`,
  `runtime/provisioning/rename-working-copy.sh`.
- `tests/test_identity.py`, `tests/test_rename_history.py`.
- ADR-002 (the dimensions this state belongs to).

## Amendments

The body above reads current; each change's full note is in [history/ADR-003-amendments.md](history/ADR-003-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-09-28 | An agent's own session writes its restart marker and its sweep record | §2, §5 rule 2: `fabric-fresh` a second `restart.json` writer; `fabric-branches` writes `branch-sweep.json` under `agent_lock` |
| 2026-10-05 | A self-contained transactional store is a writer class | §2, §5 rule 1: `episodic.db` (ADR-041) written only by `episodic.py`, through SQLite's own transactions |
| 2026-09-28 | The job list is per-agent state | §5 rule 1: `jobs.json` and its writer `update_jobs` |
