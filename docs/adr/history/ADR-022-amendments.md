# ADR-022 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-28 — An agent ends its own job with a fresh session

The owner, to the fabric-coordinator session, after asking how the
control plane could force a /clear on a session: "what i wish is that at
the end of a task/job a agent can do this on himself", then "put in the
same open pr".

A slash command comes only from the person at the keyboard, so a model
cannot /clear itself. The session is the launcher's child, though, and
the launcher already relaunches after a restart marker (the fleet
upgrades of ADR-009), resuming the stopped conversation. `fabric-fresh`
writes that marker with `fresh` true and a note and stops its own
session; the launcher, on a fresh marker, relaunches with no `--resume`
and puts the note in the opening prompt. The finished conversation stays
on disk. The command is refused outside a launched session (nothing
would bring one back) and on uncommitted changes unless `--force` (a job
not yet at its artifact). When to use it is the agent's judgement,
stated in CLAUDE.md; the owner's two choices, a refusal rather than a
warning on uncommitted changes and guidance rather than a rule on every
job, were taken as the safer defaults.
