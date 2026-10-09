# ADR-037 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-08 — Priority, blocking derived, a role pool, and taking the next job

The owner asked that an agent which closes a job looks for the next and takes it, and that the queue know priority, with a job that blocks another agent first. Asked how, the owner chose: the agent's own list, then a pool for its role; blocking derived from other agents' blocked jobs, beside an explicit priority anyone adding a job may set.

- Rule 7 adds the priority and its order, never preempting the active job and leaving a blocked one in place.
- Rule 8 derives `blocking` from the state stream: the message ids a blocked job waits on, ids only, so rule 6's "not each other's lists" holds.
- Rule 9 adds the role pool, serialized in the coordinator's control agent, with the claim checked against the claimant's own binding.
- Rule 10 is the duty to take the next job.

python-dev-01 builds it (its REQUEST, relay seq 20917, undertaken with two points this text keeps: an effectively blocking job keeps its stored priority, and the claim reads the claimant's binding).

### Amendment 2026-10-09 — A stale waiter still counts

Rule 8 said a queued job others wait on ranks blocking, but not what happens when the waiter's state record is old. #124 settled it in code (python-dev-01, on fabric-coordinator's ruling in its request thread): the waiter still counts, because its block lives in its own `jobs.json` whether or not its control agent is running to report it, and dropping the rank would hide a real wait behind an agentd restart. `fabric-jobs list` names such a waiter with the record's age and says it is stale; `runtime/control/queue.mjs` returns the stale waiters beside the waits. This entry is the record half.
