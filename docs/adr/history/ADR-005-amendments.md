# ADR-005 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-29 — code-low and code-medium are Sonnet 5.5 on plain claude

The owner asked for the two lower classes to move to Sonnet 5.5, just
released, on every agent. Its id, `claude-sonnet-5-5`, was read back
live before the change: it serves as itself at medium, through `--model`
and through the `haiku` and `sonnet` aliases the launcher exports, while
`claude-sonnet-5.5` and a bogus id are refused
(`docs/live-checks/2026-09-29-sonnet-5-5.md`). The upper classes, the
review class and the session stay on Opus 5.5; the broker column is
unchanged.

### Amendment 2026-10-07 — code-low is Haiku 5.5 on plain claude

§1 and §2's current mapping. The owner: "haiku 5.5 available, this must
be anthropic default code-low". The id and the effort were read back
(docs/live-checks/2026-10-07-haiku-5-5.md): `claude-haiku-5-5` served
through the `haiku` alias at medium, a near spelling and a control were
refused, and unlike Haiku 4.5 it takes an effort level, so routing's
no-effort row narrowed to Haiku 4.x. code-medium stays on Sonnet 5.5.
