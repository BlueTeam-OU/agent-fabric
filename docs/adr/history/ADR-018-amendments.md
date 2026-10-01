# ADR-018 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-28 — The charter tripwire runs on every branch

§6 recorded a known gap: `check_charter_authority.sh` was tested but
no CI step ran it, so its one property the repository-wide fence lacks —
reading `policies/authority.json` from the base of the diff, so that a
branch cannot appoint itself — was not in force, and
`policies/AUTHORITY.md` named it as the enforcement for charters,
briefs and the catalogue. §6 left the choice open between wiring it
into `tests/run.sh` and retiring it. An audit of the coordinator's
queue on 2026-09-28 found it still open; it is wired, beside the
`.agent-fabric/` tripwire, with the same base.

### Amendment 2026-09-30 — Doppler is retired: the stores replace it

Doppler is removed (ADR-038, agent-fabric #69): the reference names credentials and the stores as this role's, not the Doppler project.

### Amendment 2026-10-01 — A contributor role commits its entry's paths

The owner asked for a Python developer to share the port of the
fabric's bash (ADR-040) and its new tooling, and chose, of the two
options put to them, to let that role commit agent-fabric's code rather
than only send patches. The fence admitted no role but the coordinator
outside a locale: a second role could not make one commit, and
`policies/AUTHORITY.md`'s "open a pull request" was a step no other role
could take. The carve-out names the role and its paths in
`policies/authority.json`, read from the base in CI as the owner role
already was; definitions stay out of every entry, and every contributed
commit reaches main inside the coordinator's pull request, under its blind
review.
