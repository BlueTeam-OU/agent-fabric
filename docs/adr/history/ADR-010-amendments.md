# ADR-010 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-30 — Doppler is retired: the coordinator keeps its own store, a parent's

Doppler is removed (ADR-038, agent-fabric #69): what the coordinator keeps is its own store and the provisioning of each child's, not Doppler administration.

### Amendment 2026-10-19 — full-suite: one full local test run per host

§5 rule 9. With the host's load near 90 on 10 cores (2026-10-19), a
full `tests/run.sh` failed timing-sensitive suites that pass alone
(test_launch, test_new_agent, test_section_groups, test_self_kill_guard,
test_roots_readers, test_fabric_lease_cli) for every account that ran
one, so a red full run had stopped meaning a defect. A full local run
now takes `full-suite` and waits for it (`--wait`, against rule 10's
fail-fast default, on purpose: a queued run is the point), and the
lease ends with the run, the wrapper holding it at the run's pid. CI,
partial runs and the opt-out are untouched.
