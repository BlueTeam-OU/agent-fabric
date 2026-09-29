# ADR-006 — Effort is routed

**Date:** 2026-09-23
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #51 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** fabric-coordinator, on the Opus 5.5 measurement of 2026-09-23; the owner (every class and session at medium, 2026-09-25)
**Scope:** routing/effort.json; the provider adapters' per-model effort tables in tools/fabric/routing.py; runtime/claude-code/install-agent-files.sh (the `effort:` line); runtime/openrouter/launch (`--effort`, AGENT_FABRIC_LAUNCH_EFFORT, the environment refusals); the committed-settings guard; bin/fabric-status and bin/fabric-model
**Pillar:** P1
**Evidence:** docs/live-checks/2026-09-23-opus-5-5.md, docs/live-checks/2026-09-23-effort-registry.md

## 1. Context and Problem

The fabric pinned a model per class and said nothing about how hard that
model thinks. That was invisible for exactly as long as every pinned model
happened to default to the same level. Measured through one launcher and
one profile, changing one thing, on 2026-09-23: `claude-opus-5` defaults
to effort `high`, `claude-opus-5-5` to `medium` — and the harness's own
model registry, read out of the binary, says the same. Moving `code-high`
to Opus 5.5 would have dropped every session a level of thinking: no
commit, nothing to review, and a symptom that reads as a worse model
rather than a changed default.

Reading the harness further showed the traps: `CLAUDE_CODE_EFFORT_LEVEL`
outranks `--effort`, `/effort` and an agent file's `effort:`, and reaches
every subagent through the process environment; `unset` and `auto` are
values meaning "use the model's default", not absence; the Agent tool
takes no effort on a dispatch.

## 2. Decision

**A model id is not the whole routing decision.** Each class also decides
a reasoning effort, in its own file, `routing/effort.json`, in one
vocabulary for every provider:

```
none < minimal < low < medium < high < xhigh < max
```

— the union of the vendors' scales, an ordinal, never a quantity. What a
class asks for is clamped **by the fabric, before the request leaves**, to
what its model admits, by the provider's adapter in
`tools/fabric/routing.py` (`effort_for`), per (provider, model): the
vendor's own documented mapping where there is one, in either direction
(GLM-5.2 serves `medium` as `high`); else down to the nearest level below;
and a request below the model's floor is **raised** to that floor, since
sending nothing would hand the vendor its default. A level lost, raised
or inexpressible is never applied silently: it must be written down as a
committed override with a note.

The level reaches a subagent through its agent file's `effort:` line,
written by `install-agent-files.sh`, and the session through `--effort`,
stamped as `AGENT_FABRIC_LAUNCH_EFFORT`.

**Today** every class and every session asks
`medium`. On plain claude the upper classes are Opus 5.5 at medium, its
own default, and the lower two are Sonnet 5.5 at medium, which it admits; on the broker `code-low` is committed at `low` (GLM-5.3-Flash has
no medium), and the other classes are served `high` by their models'
documented mapping — one level above what they ask, so no override. On
plain claude a class therefore no longer picks a model or a level; it
still picks the alias, the worktree rule and whether a dispatch asks. The
machinery stays whole, so a later split is one edit per file.

## 3. Alternatives Considered

- **Pin `--effort high` on the launcher.** Not taken: it fixes this bump
  and leaves the next vendor default change to be found the same way.
- **Effort as a column per provider**, like models. Rejected: how much
  thinking a class needs is a property of the work; how a provider spells
  it is the adapter's.
- **Let each vendor handle an unsupported level.** Rejected: OpenAI
  answers HTTP 400, xAI and Claude Code quietly drop a level,
  GLM-5.3-Flash errors, DeepSeek remaps — one routing decision would mean
  different things depending on who serves it.
- **`CLAUDE_CODE_EFFORT_LEVEL` as the channel.** Rejected: it flattens
  every per-class decision at once.

## 4. Rationale

A vendor's default is the vendor's; what a class gets is the fabric's, or
it is nobody's. Making the level a routed, committed value turns a
vendor's default change into a diff someone reviews. The read-back after
the dimension landed (e59d0ba) showed the model move without the thinking
move: Opus 5.5 at `high` because routing asked for it.

## 5. Binding Rules

1. `routing/effort.json` holds each class's level and the session's, in
   the seven-level vocabulary; no other file decides it.
2. A provider's adapter declares, per model, the levels it admits; the
   clamp is computed by the fabric before the request leaves.
3. A clamp that loses a level, or raises one to the model's floor, makes
   `routing.py check()` fail until the served value is written into
   `providers.<p>.classes.<class>` with a note saying why; a model that
   expresses no effort at all needs an explicit `null` there, with its
   note. A downgrade, or a raise to the floor, is a commit, never a
   computation; a vendor's own documented mapping is applied as
   documented. The session's level is judged the same way on the
   session's model, acknowledged at `providers.<p>.session` with its
   note in `providers.<p>.notes.session` (A 2026-09-28).
4. A class's level reaches its subagent only through its agent file's
   `effort:` line, written by `install-agent-files.sh`; a hand-written
   `effort:` in a committed source is a lint finding. A model with no
   effort capability gets no line.
5. The session's level rides `--effort` and is stamped as
   `AGENT_FABRIC_LAUNCH_EFFORT`; a caller's own `--effort` wins and is what
   gets stamped.
6. The launcher refuses `CLAUDE_CODE_EFFORT_LEVEL` in any value,
   `unset` and `auto` included. The committed-settings guard refuses
   `effortLevel`, `maxEffortLevel` and `modelSettings` (a committed
   `maxEffortLevel` cannot be raised back by a launch: the lowest across
   scopes wins).
7. Effort is never set per dispatch. The per-agent layer is
   `fabric-model set <class>-effort <level>`; `fabric-status` prints the
   level beside the model and compares the harness's `CLAUDE_EFFORT` with
   the launcher's stamp.

## 6. Consequences

- A subagent's applied level is recorded in its own transcript (the
  `"effort"` field of `subagents/agent-<id>.jsonl`), so the per-class
  level is checkable after the fact; `CLAUDE_EFFORT` is the session's
  only.
- On the broker, `code-high`, `code-plan` and `code-review` today differ
  in neither model nor effort — true of the current column, not of the
  design. Tests of the machinery run on an earlier column
  (`tests/fixtures/routing-distinct/`), where the classes still differ.
- Another harness fits by its channel: Codex CLI has no `--effort` and no
  per-agent file, so its adapter would be `effort_channel = "session"`
  (`-c model_reasoning_effort=<level>`); vocabulary, tables, clamp and the
  committed-downgrade rule sit above the channel.

## 7. Future Evolution

- A drift check comparing the asked level with the one recorded in the
  transcript can now be built; it is later work.
- Not established: whether a level a model does not admit is recorded
  after the harness's own clamp or before it; OpenRouter's translation of
  effort for DeepSeek (GLM-5.2's was measured: `max` distinct, `xhigh` not
  mapped to `max`); whether a settings `maxEffortLevel` clamps silently.

## 8. Decision Status

Accepted and in force, with every class at `medium` (§2).

## References

- `routing/effort.json`; `tools/fabric/routing.py` (the adapters,
  `check()`); `runtime/claude-code/install-agent-files.sh`;
  `runtime/openrouter/launch`; `policies/check_repo_settings_carry_no_model_pins.sh`;
  `bin/fabric-status`, `bin/fabric-model`.
- `docs/live-checks/2026-09-23-opus-5-5.md` (the measurement, the control,
  the read-back after e59d0ba), `docs/live-checks/2026-09-23-effort-registry.md`
  (the precedence chain, the registry, the transcript field, Codex, GLM-5.2).
- ADR-005 (the model half of the same class decision).

## Amendments

The body above reads current; each change's full note is in [history/ADR-006-amendments.md](history/ADR-006-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-09-28 | The session's level is judged like a class's | §5 rule 3: `check()` judges the session on its own model; `providers.<p>.session` |
