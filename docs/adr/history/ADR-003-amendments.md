# ADR-003 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-28 — An agent's own session writes its restart marker and its sweep record

The blind review of the pull request that added `fabric-fresh` and
`fabric-branches` found both writing under `agents/<login>/` with their
own temporary-and-rename, outside `runtime/identity.py`, and §2 still
naming the control agent as the only writer of `restart.json`. Both now
load `identity.py`: `fabric-fresh` writes the marker with
`atomic_write`; `fabric-branches` updates `branch-sweep.json`, one date
per working copy, as a read-modify-write under `agent_lock`, so two
sweeps of one login no longer lose a date. §2 and rule 2 name the
second `restart.json` writer.

### Amendment 2026-09-28 — The job list is per-agent state

ADR-037 gives each login a job list, `agents/<login>/jobs.json`. It is
per-agent state like the binding: `runtime/identity.py` gains its reader
and its writer (`read_jobs`, `update_jobs`), the writer holds
`agent_lock`, and the reader refuses a list naming another agent or
written on another host, as `read_binding` does.

### Amendment 2026-10-05 — A self-contained transactional store is a writer class

Rule 1 said every Python write under `agents/<login>/` goes through
`runtime/identity.py`, with the Node control agent the one exception.
ADR-041's episodic journal (`episodic.db`) has been written directly by
`tools/fabric/episodic.py` since it landed: a SQLite database in WAL mode
owns its atomicity and locking, and a temporary-and-rename or a file
lock around it would only duplicate or defeat them. An external review
(2026-10-05) named the record and the tree disagreeing. The record now
names the class (a self-contained transactional store) and its one
member, with the guarantees it keeps instead: one writer module, short
transactions, private modes, its own schema version.

