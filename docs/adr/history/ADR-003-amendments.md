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

### Amendment 2026-10-05 — The GZCoord logs are a writer class

The review of agent-fabric#99 found two per-agent files written outside
`runtime/identity.py` and named in no rule: `journal-bypass.jsonl`, new
with ADR-041 rule 10, appended by `bypass.py` under `agent_lock`; and the
older send ledger `gzcoord-sent.jsonl`, appended by `send.py` and trimmed
by a read-then-rewrite that holds no lock. Rule 1 now names them as a
class, with how each is written, and records the ledger's unlocked trim
as a gap to close rather than as conforming.


### Amendment 2026-10-30 — The action ledger has two writers, serialized by a flock on the state directory

§2 said the control agent, in Node, wrote `actions-seen.json` and
`restart.json` with no `agent_lock`, and that what serialized them was
that one control agent runs per account. Two things had made that
false. The control code is Python since ADR-040's Wave 8 (the Node was
deleted in #170); it kept its own temporary-and-rename writers. And
agent-fabric #418 added `bin/fabric-op`, the break-glass path that runs
one signed action on an account with no relay (ADR-029 rule 19): it
decides through agentd's own `accept()` against the same ledger, so the
ledger now has two writers in one account. #418 serializes them with
an exclusive `flock` on the state directory (`ActionLedger._locked`),
and records a request by an atomic check-and-record under it
(`ActionLedger.claim`), so one writer never writes back a floor read
before the other raised it, and a request reaching both paths is run
once; `accept()`'s earlier read of the floor is unlocked, and the
claim checks it again. `fabric-op` also appends a journal,
`fabric-op.jsonl`, beside the older append-only `account-switch.jsonl`.
The control code's other files are replaced whole by temporary and
rename. One of them is unserialized: the role pool, `pool.json`, which
is rewritten with no lock. Its module says the writes are serialized
because agentd makes them in its loop, but `pool-add` runs in a thread
beside that loop, which answers `pool-claim`. So one control agent
already races with itself, and `fabric-op` adds a second process. Rule
2 names this as a gap to close. The re-review of #422 found the first
wording, which said the race came only from `fabric-op` and that every
other file was an append-only log. §2 and rules 1 and 2 now say this;
the Scope line names the control code's state writers.

Reported by python-dev-04, the author of #418 (REQUEST 01a18b3f).

### Amendment 2026-10-30 — The role pool is rewritten under its own lock

The amendment before this one named `pool.json`'s unlocked
read-modify-write as a gap: `pool-add` runs in a thread beside the read
loop that answers `pool-claim`, and `fabric-op` can run a `pool-add` in
a second process, so one of two updates could be lost. agent-fabric
#423 closes it: every read-modify-write of the pool holds an exclusive
`flock` on `pool.json.lock` beside it (`pool._locked`), and a holder
that does not let go within 5 s is a refusal that changes nothing. The
lock is a file beside the pool, not the state directory, whose `flock`
is the action ledger's. §2 and rule 2 now say this.

Reported by python-dev-04, the author of #423 (REQUEST 01a18bc6).

### Amendment 2026-10-31 — A lock file is not state

The blind review of agent-fabric #429, round 1, asked whether the lock
files under `agents/<login>/` fall under rule 1's "no caller opens a
file for writing". `pool.json.lock` (`pool._locked`) and the control
code's `busy-marker`, `busy-restart` and `busy-sync`
(`control/busy.py`) are opened `O_RDWR | O_CREAT` outside
`runtime/identity.py`, and so is `identity.py`'s own `.lock`. Read
literally, the rule forbids all of them, `agent_lock` included; read
for its purpose (no lost update, no torn file), it never meant them,
since no byte of a lock file is written or read. The decision: a lock
file is not state, and rule 1 does not reach it, on three conditions
that keep the lock sound. Its content is never written or read. It is
opened without `O_TRUNC`, mode 0600. And it is never removed or
replaced: a process holding the unlinked file and another opening its
successor would each hold "the" lock, which is the one way a lock file
can fail. The files named meet all three today. `O_NOFOLLOW` and
`O_CLOEXEC`, which `pool.py` and `busy.py` add, are good practice, not
conditions: `agent_lock` predates them, and the state directory is
0700.

### Amendment 2026-11-01 — The session hooks write through `identity.py`, under their own lock files

Found while reading the per-agent writers for job j479: the two hooks
that tell the control agent what each session is doing,
`runtime/claude-code/hooks/session-state.py` (`session-state.json`) and
`context-sample.py` (`session-context.json`), rewrote their files under
`agents/<login>/` by a temporary and rename of their own, outside
`runtime/identity.py` and unnamed in this record. The temporary,
`<file>.<pid>`, was not removed when a write failed, so a full disk left
one behind per failing process. Rule 1 asks a new state file for its
writer in `identity.py`, not a writer class of its own, and the hooks
can load it: both now replace their file with `atomic_write`, mode 0600,
loading `identity.py` by the hook's own place in the tree only when there
is something to write, since `PreToolUse` fires on every tool call and
mostly writes nothing.

Rule 2 is where they differ, and stay different: neither takes
`agent_lock`. A hook may never stand in a session's way, and a binding
writer holds that lock for as long as a bind takes. Each serializes its
read-modify-write on a lock file of its own, `session-state.json.lock`
(a 1 s wait, then the event is dropped) and `session-context.json.lock`
(no wait), the same shape as `pool.json.lock`. Both lock files were
opened with the umask's mode, 0644 under the usual 022; they are now
created 0600, without `O_TRUNC`, with `O_NOFOLLOW` and `O_CLOEXEC`, which
meets the 2026-10-31 conditions for a lock file that is not state.
`tests/test_session_state.py` and `tests/test_context_sample.py` hold
the writer, the lock file's mode and a failed write that leaves the
previous file whole and no temporary.
