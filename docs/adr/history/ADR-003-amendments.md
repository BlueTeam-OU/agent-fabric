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
