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

### Amendment 2026-11-10 — `CLAUDE_CODE_SUBAGENT_EFFORT` is refused like `CLAUDE_CODE_EFFORT_LEVEL`

The pin's move to Claude Code 2.1.322 (ADR-043, A 2026-11-10) brings a variable that 2.1.311 does not read; the changelog embedded in the 2.1.322 binary lists it under 2.1.316. Read in the 2.1.322 binary, `CLAUDE_CODE_SUBAGENT_EFFORT` sets the level of a subagent whose definition names no effort, instead of the session's. It is skipped for a definition that has one. Every class file the fabric writes has one, unless the class's model has no effort capability (rule 4), so the variable reaches the harness types (`Explore`, `Plan`, `general-purpose`), the language-culture logins' `locale-worker`, whose file names no effort by design, and any class on a model with no effort line. A launch's environment reaches every subagent, so one value there would move all of them off the session's routed level, with nothing in routing saying so. It is refused in any value, as `CLAUDE_CODE_EFFORT_LEVEL` is, `inherit` and empty included: a value that changes nothing today is still a channel routing does not see. The live read-back is `docs/live-checks/2026-11-10-claude-code-2-1-322-readback.md`. The launcher's refusal is python-dev's code (REQUEST `01a1c63c`). The committed-settings guard's `env` names are the coordinator's, and moved in the same change.
