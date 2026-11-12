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

### Amendment 2026-10-09 — python-dev's session is Sonnet 5.5, a role layer

The owner made Sonnet 5.5 python-dev's session model after the pilot (2026-10-08, docs/live-checks/2026-10-08-python-dev-sonnet-pilot.md); #130 put it in `routing/profiles.json` as a role layer. §2 lists the exceptions to the default session, and did not name this one (#130's blind review, F4). The capability classes are unchanged.

### Amendment 2026-11-09 — architect-cto-01's session is Fable 5.2

The owner, 2026-11-09: Fable 5.2 had just become available, and architect-cto moves to it. The id was read back before the change (docs/live-checks/2026-11-09-fable-5-2.md): `claude-fable-5-2` is served, at low and at medium effort, while the dotted spelling and a made-up control are refused. Claude Code 2.1.311 printed `unrecognized_model` on stderr for the low-effort probe and the control, and served `claude-fable-5-2` at both levels. Only the agent layer in `routing/profiles.json` moves. The capability classes, the fable alias's export (code-plan's Opus 5.5) and the session's medium effort are unchanged.

### Amendment 2026-11-10 — architect-cto-01's session is Opus 5.5 again

The owner, 2026-11-10: architect-cto-01's session goes back to Opus. The pinned Claude Code, 2.1.311, does not know Fable 5.2. Its session start warned that `claude-fable-5-2` "isn't recognized" and that it assumed a 200k context. The 2026-11-09 read-back had already seen the `unrecognized_model` line. The agent entry in `routing/profiles.json` is removed, so the session takes the anthropic column's default, `claude-opus-5-5`, as every other agent's does. Fable 5.2 can come back as an agent layer once a pinned harness knows the id. The capability classes, the aliases and the session's medium effort are unchanged. The change reaches the session at its next launch.

### Amendment 2026-11-10 — architect-cto-01's session is Fable 5.2 again, with the pin

The owner, 2026-11-10: the agent layer the amendment before this one removed comes back with the harness pin's move to 2.1.322 (ADR-043, A 2026-11-10). That amendment said the layer could return once a pinned harness knew the id. The read-back on 2.1.322 (`docs/live-checks/2026-11-10-claude-code-2-1-322-readback.md`, case F1) served `claude-fable-5-2` with no `unrecognized_model` line, while the installed 2.1.311, the control, printed it. `routing/profiles.json` names the layer as it did on 2026-11-09. The classes, the aliases and the session's medium effort are unchanged. It reaches architect-cto-01's session at its first launch after both the fabric and the harness are upgraded on that account. A launch on the fabric before the harness upgrade would start Fable 5.2 on 2.1.311 with its 200k assumption again, so that account's harness is upgraded in the same pass.

### Amendment 2026-11-12 — Delegation to subagents is the default for every role

The owner, 2026-11-12: delegation to subagents is the default for every role. The fleet's text had told every agent that dispatch is opt-in per task and that review is the only standing exception, so agents did all work serially in their own context and used subagents only for review; the Claude Code Agent tool's own description ends "When in doubt, don't spawn", and a session read that caution as the fleet's rule. §2 and §6 now say the default, and §5 rule 11 binds it: work over a few lines with a clear contract goes to a worktree-isolated class agent in the background, wide searches to Explore, independent pieces in parallel; the session keeps decisions, messages, reviews and short edits and commits what lands. Unchanged: the class and its alias on every dispatch, the review class on fable without isolation, writes partitioned by file set, the guard's ask on the premium tier, and Workflow scripts only on the user's explicit opt-in.

### Amendment 2026-11-12 — code-plan on Fable 5.2, plan and review at high effort

The owner, 2026-11-12, after reading Anthropic's model and effort guidance: the model overview recommends Fable 5.2 "for demanding reasoning and long-horizon agentic work" and reports good results with it "as the planner and orchestrator for other models", and the effort page starts Fable 5.2 at `high`, where most of its gain is. `code-plan` therefore moves from Opus 5.5 to `claude-fable-5-2` on plain claude, and the `fable` alias, which `code-plan` rides, binds to it. The review class stays Opus 5.5 by the owner's choice (cost: Fable 5.2 is $8/$40 per MTok, twice Opus 5.5); its model reaches the reviewer through its agent file, not the `fable` export (§5 rule 5), so the move does not touch it. Both classes ask `high` (ADR-006, A 2026-11-12). Evidence so far: architect-cto-01's session was read back serving `claude-fable-5-2` at medium on 2026-11-12, a session and not a `code-plan` dispatch. Not yet measured: a `code-plan` dispatch served by Fable 5.2 at high and a `code-review` dispatch served by Opus 5.5 at high, after the next launch; docs/live-checks/2026-11-12-fable-5-2-code-plan.md holds both as pending. Unchanged: every other class, the sessions, every other provider.
