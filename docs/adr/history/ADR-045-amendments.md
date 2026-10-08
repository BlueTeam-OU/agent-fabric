# ADR-045 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-08 — The engine root honours AGENT_FABRIC_ROOT until stage 4

Rule 1 said `engine_root()` is the code's own location. The seam's first
implementation (python-dev-03, #119) kept honouring `AGENT_FABRIC_ROOT`
when it is set: every wrapper and test fixture sets it, and in production
it names the code's own location anyway, so dropping it would have
rewritten every fixture for no change in behaviour. It is accepted as a
transition until stage 4, when the operator's data moves out and the
variable stops meaning both trees. Meanwhile a fixture that stands in
for instance data sets `AGENT_FABRIC_OPERATOR`, so the double meaning the
record ends is not extended.
