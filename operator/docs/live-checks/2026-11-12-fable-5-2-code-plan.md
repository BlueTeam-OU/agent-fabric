# 2026-11-12: code-plan on Fable 5.2, plan and review at high

**Why.** The owner moved `code-plan` from Opus 5.5 to `claude-fable-5-2` on plain claude and raised `code-plan` and `code-review` from medium to high, after reading Anthropic's model and effort guidance (ADR-005 and ADR-006, A 2026-11-12). The model overview recommends Fable 5.2 "for demanding reasoning and long-horizon agentic work" and reports good results with it "as the planner and orchestrator for other models". The effort page starts Fable 5.2 at `high`, where most of its gain is, and names `high` for "complex reasoning, difficult coding problems, agentic tasks". `code-review` stays on `claude-opus-5-5` by the owner's choice; Fable 5.2 costs $8/$40 per MTok, twice Opus 5.5. ADR-005 §5 rule 10 asks that a model move into routing only after it is read back served through the launcher, with a control showing the pass is not a fallback; this file records how far that has come.

**Measured so far, 2026-11-12.**

| what | how | result |
|---|---|---|
| Fable 5.2 on a session | `fabric-status` in architect-cto-01's session | serves `claude-fable-5-2` at effort `medium`, confirmed |

That is a session, not a `code-plan` dispatch: it shows the harness pin and the account serve the model, and says nothing about the `fable` export reaching a subagent or about effort `high`.

**Not yet measured.** Both need a launch after this change, because the `fable` export and the agent files' `model:` and `effort:` lines are written at launch.
- A `code-plan` dispatch served by `claude-fable-5-2` at effort `high`.
- A `code-review` dispatch served by `claude-opus-5-5` at effort `high`, with the model coming from its agent file and not the `fable` export (ADR-005 §5 rule 5).

## Read-back

| dispatch | expected | served | control | status |
|---|---|---|---|---|
| `code-plan` | `claude-fable-5-2`, effort `high` | pending | pending | pending |
| `code-review` | `claude-opus-5-5`, effort `high` | pending | pending | pending |

Until both rows are filled, ADR-005 rule 10 is met for the session only. The rows are filled from the subagent transcripts of the first dispatches after the next launch, with a control that shows the served model is not a fallback.
