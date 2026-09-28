# ADR-006 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-28 — The session's level is judged like a class's

`routing.py check()` judged every class's level against its model but
never the session's: `session_effort()` clamped it at launch and nothing
refused a session level its model would lose (PE1 of the #40 review,
still open at the coordinator's 2026-09-28 queue audit). Measured before
the change: the session asks for `medium`; Opus 5.5 applies it, and
DeepSeek V4 Pro serves `high` by its own mapping — neither is a finding
under the class rule, so the check adds none today. `xhigh` on the
broker would be served `high` and `none` on Opus 5.5 raised to `low`;
both are now refused until written down.
