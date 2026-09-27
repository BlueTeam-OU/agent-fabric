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
remove it, never edit it in place.

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
   `identity` and calls `atomic_write`, `update_binding` or
   `append_history`. A new state file gets its writer added to
   `runtime/identity.py`, not a rewrite in place elsewhere. The Node
   control agent is the named exception (§2), and writes only by
   temporary and rename.
2. Every read-modify-write of per-agent state holds `agent_lock`, except
   the Node control agent's own files (§2), which only it writes and the
   launcher only consumes.
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
