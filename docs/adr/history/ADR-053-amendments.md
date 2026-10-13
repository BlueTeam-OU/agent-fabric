# ADR-053 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-13 — the sandbox proven before the run; Codex's own fetches off

§5 rule 2 gains the sandbox proof and rule 3 the features switched off.
Rule 2 said the sandbox was read-only and nothing checked it started;
the first two Codex reviews ran with no tool host and read nothing
(#229), so a run's preconditions are now proved, not assumed. Rule 3
said the gateway was Codex's only upstream, and a 30-second strace of
`codex exec` against a local gateway showed Codex fetching
`github.com/openai/plugins.git` on its own: 11 git executions and 7
non-loopback connects with the default features, none with the five
features off (docs/live-checks/2026-10-13-codex-engine-egress.md).
Built in `tools/fabric/review_codex.py` (`prove_sandbox`, the
`[features]` block of the engine's Codex home) by python-dev-03.
