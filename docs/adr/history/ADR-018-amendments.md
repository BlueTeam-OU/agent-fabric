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
