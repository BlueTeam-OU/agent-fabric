# 2026-09-23 — where Claude Code's effort actually comes from, read out of the binary

`2026-09-23-opus-5-5.md` measured that Opus 5 runs at `high` and Opus 5.5
at `medium` through the same launcher and profile, and concluded that the
model id alone is not the routing decision. This note is the second,
independent read-back behind `routing/effort.json`: not a measurement of
two sessions but the harness's own tables, read out of the installed
binary (`~/.local/share/claude/versions/2.1.280`, 233 MB, `grep -a` plus
a single-pass extractor). It is what the adapter's per-model rows are
based on, and it is the control on the measurement — two methods, one
answer.

## The precedence chain

`aS(model, configured, {turnEffort, hookEffortValue})`, deminified:

```
1. hookEffortValue      internal: a retry that re-decides effort (NOT a user hook)
2. CLAUDE_CODE_EFFORT_LEVEL   the environment — highest thing a human sets
3. turnEffort           --effort / /effort, this turn
4. configured           the agent file's `effort:` / the session's level
5. the model's own default_effort   (and "high" if it has none)
```

Two things this settles that documentation did not:

- **The environment outranks the agent file.** A launcher that exported
  `CLAUDE_CODE_EFFORT_LEVEL` would flatten every per-class decision the
  fabric makes, because process environment reaches every subagent —
  the same bug `CLAUDE_CODE_SUBAGENT_MODEL` is already fenced for
  (`runtime/openrouter/launch`). The fabric must never export it.
- **`unset` and `auto` are values, not absence.** `ZD()` maps either
  (case-insensitively) to `null`, and `null` in `aS` means *skip the
  configured level and use the model's own default*. So
  `CLAUDE_CODE_EFFORT_LEVEL=auto` in an account's shell profile does not
  disable the variable — it silently defeats every `effort:` the fabric
  writes. It belongs in the launcher's environment scan beside the rest.

`hookEffortValue` is named as if a hook could set it. It cannot: the only
caller compares a retry's effort with what was sent
(`r.effort !== e.sent.effort`), which is the "latching unsupported and
retrying without it" path. No hook event carries an effort override.

## The clamp, and where it is decided

```js
D(level, model):  level == "max"   && !K$(model) -> "high"
                  level == "xhigh" && !y6(model) -> "high"
```

`K$` and `y6` test the model's `max_effort` and `xhigh_effort`
capabilities. So the silent downgrade is **per model and only ever from
`max`/`xhigh` to `high`** — the lower levels are passed through
untouched. The canonical scale is `["low","medium","high","xhigh","max"]`
(five; no `none`, no `minimal` — those exist on other vendors, which is
why `routing/effort.json` declares the union and each adapter declares
its own subset).

## The registry

Every Claude model the build knows, with the effort levels its
`capabilities` list admits and its `default_effort`:

```
claude-3-5-haiku-20241022      no effort control
claude-3-5-sonnet-20241022     no effort control
claude-3-7-sonnet-20250219     no effort control
claude-fable-5                 levels=low/medium/high/xhigh/max    default=high
claude-fable-5-1               levels=low/medium/high/xhigh/max    default=high
claude-haiku-4-5-20251001      no effort control
claude-mythos-5                no effort control
claude-mythos-5-1              levels=low/medium/high/xhigh/max    default=high
claude-opus-4-1-20250805       no effort control
claude-opus-4-20250514         no effort control
claude-opus-4-5-20251101       no effort control
claude-opus-4-6                levels=low/medium/high/max          default=(unset -> high)
claude-opus-4-7                levels=low/medium/high/xhigh/max    default=xhigh
claude-opus-4-8                levels=low/medium/high/xhigh/max    default=high
claude-opus-5                  levels=low/medium/high/xhigh/max    default=high
claude-opus-5-5                levels=low/medium/high/xhigh/max    default=medium
claude-sonnet-4-20250514       no effort control
claude-sonnet-4-5-20250929     no effort control
claude-sonnet-4-6              levels=low/medium/high/max          default=(unset -> high)
claude-sonnet-5                levels=low/medium/high/xhigh/max    default=high
```

`max_effort` and `xhigh_effort` are separate capabilities, which is why
4.6 stops at `max` and 4.7 does not. A model whose list lacks `effort`
entirely is gated out by `L_()` before a request is built: **no level is
ever sent for it**, which is a stronger and narrower statement than
"rejects the parameter" — the earlier wording in `routing/effort.json`,
now corrected.

What this decides, row by row, is `AnthropicAdapter.effort_by_model`.
All four of its globs are confirmed here, including the two that looked
like guesses: `claude-opus-4-6*` and `claude-sonnet-4-6*` really do stop
at `max`.

**It also corroborates the 09-23 measurement from a second direction:**
`claude-opus-5` carries `default_effort:"high"` and `claude-opus-5-5`
carries `default_effort:"medium"`. The session measurement and the
binary's own table agree, so the level drop is a property of the model
entry and not of that afternoon's two sessions.

One consequence the fabric now states out loud: `claude-sonnet-5`'s own
default is `high`, and `code-medium` asks for `medium`. The fabric is
deliberately asking that class for less thinking than the vendor would
give it. That is the dimension doing its job — a level chosen rather
than inherited — but it is a real reduction, so it is written into
`routing/effort.json` as a note rather than left to be discovered.

## Control: where a subagent's effort can and cannot be read

**Corrected the same day.** This section first said a subagent's effort
is observable nowhere. That was drawn from one control dispatch, on
`code-low` — Haiku 4.5, the one pinned model with **no** effort capability,
so the one sample that could not show the field. It was wrong.

Measured properly, three dispatches' JSONL transcripts
(`~/.claude/projects/<cwd>/<session>/subagents/agent-<id>.jsonl`):

```
code-low     haiku-4-5    file: no effort: line   transcript: no "effort" field at all
code-review  opus-5       file: effort: high      transcript: "effort": "high" on every entry
code-medium  sonnet-5     file: effort: medium    transcript: "effort": "medium"
                          parent session running at high (CLAUDE_EFFORT=high)
```

The last row isolates the channel: the agent file said `medium`, the
session that dispatched it ran at `high`, and the subagent recorded
`medium`. So an agent file's `effort:` reaches the subagent **and
overrides the session's level**, and the transcript is its read-back.
That is the plan's check A, done end to end.

What stays true: `CLAUDE_EFFORT` is exported to the **session's** tools
only — a subagent's environment carries the four `ANTHROPIC_DEFAULT_*`
pins and nothing about effort.

Consequences, replacing the ones first written here:

- The plan's step 5, a drift check comparing asked with applied, **can**
  be built: the applied level is in the transcript. It is later work, not
  impossible work.
- The fabric-side clamp and `check()`'s refusal are the first line of
  defence, not the only one.

The `ANTHROPIC_DEFAULT_OPUS_MODEL=claude-opus-5` the subagent reported is
this session's launch-time export, not the `claude-opus-5-5` now in the
agent's local layer — an independent confirmation that a subagent
inherits the launcher's environment, and that a model change needs a
relaunch (`bin/fabric-status` says so as DRIFT).

## A second harness: the channel is the thing that differs

`effort_channel` on the adapter exists because effort reaches a model
differently on different harnesses, and that claim was worth testing
against something that is not Claude Code. Codex CLI v0.156.1, installed
into a scratch prefix and read:

- **No `--effort` flag at all.** Its top-level options are `-m/--model`,
  `-p/--profile`, `-c key=value` and sandbox/approval switches.
- Effort is a **configuration key**, `model_reasoning_effort`, set with
  `-c model_reasoning_effort=<level>`, in `~/.codex/config.toml`, or in a
  named profile (`ConfigProfile` carries it, as it carries `model`).
- There is a **second** key, `plan_mode_reasoning_effort` — a different
  level for a different kind of work, which is the same idea as a
  capability class, reached by an entirely different mechanism.
- It has no per-agent-file equivalent, so a **per-class** effort is not
  expressible on it at all; only a session-or-profile level is.
- `-c model_reasoning_effort=bogus` was accepted and the session started.
  The value is not validated by the CLI, which is one more reason the
  clamp belongs to the fabric: on an OpenAI model an unsupported level is
  an HTTP 400 at the far end of the run, not an error at launch.

So a Codex adapter would be `effort_channel = "session"` and would emit
`-c model_reasoning_effort=<level>` where the Claude Code adapter emits
`--effort <level>` and an `effort:` line per class. Nothing else about
the design changes: the vocabulary, the per-model tables, the clamp and
the committed-downgrade rule are all above the channel. That is what the
field is for, and it survives contact with a harness whose shape is
different in exactly the way that matters.

## The broker's effective level, measured rather than read

Z.ai documents GLM-5.2 as collapsing `low`/`medium` to `high` and `xhigh`
to `max`; OpenRouter's own model page claims it takes only `high` and
`xhigh`; OpenRouter publishes no translation table for Z.ai. Three
sources, three different claims — so it was measured.

Four requests per level through `openrouter.ai/api/v1/chat/completions`
with `reasoning: {effort}`, one reasoning-heavy prompt, `temperature: 0`,
`max_tokens` high enough not to truncate, reading
`native_tokens_reasoning` back from `GET /api/v1/generation`:

```
medium   118  252  647  730
high      18  101  551  620
xhigh    506  515  802  819
max      900 1509 2604 4001
```

What this establishes:

- **The broker forwards effort and GLM-5.2 honours it.** `max` is a
  different population from everything else — its lowest sample (900) is
  above every other sample taken (830 at most). The Anthropic-shaped
  endpoint really does re-emit the field upstream.
- **`xhigh` is NOT mapped to `max`.** Four of four `xhigh` samples sit in
  the same band as `medium` and `high`, and none approaches `max`. That
  contradicts Z.ai's documented `xhigh -> max`, and the adapter's GLM-5.2
  row has been corrected to remap `xhigh` to `high` with the rest.
- **`medium`, `high` and `xhigh` are not distinguishable at this sample
  size.** Their ranges overlap almost completely (one `high` run spent 18
  reasoning tokens, another 620). This is *consistent with* the
  documented collapse of the lower levels into one, but four samples
  against that variance do not prove it, and this note does not claim it.

The first attempt measured nothing and is worth recording as the trap:
with `max_tokens: 40` every level returned exactly 40 reasoning tokens,
because the model was still thinking when the response was truncated. A
saturated ceiling reads as "no difference between levels" and is
indistinguishable from the effort being ignored.

## What is not established here

- That a level the model does not admit is recorded after the harness's
  own clamp or before it. Every measured dispatch asked a level its model
  admits, so the recorded value and the asked one could not differ. The
  agent frontmatter field is a **strict enum**, not loosely typed:
  `effort: Fe([V(["low","medium","high","xhigh","max"]), int])`, and the
  loader rejects anything else ("has invalid effort '…'. Valid options:
  low, medium, high, xhigh, max or an integer"). The looser text quoted
  here at first — `low, medium, high, max, or an integer` — is the
  skill/command `effort` field's, a different field. Corrected after the
  blind review of #31 read it out of 2.1.280; verified the same way.
- Anything about the broker path. OpenRouter's translation of
  `output_config.effort` for GLM and DeepSeek is still unmeasured;
  `routing/effort.json` carries the committed downgrade for `code-plan`
  from the vendors' documentation, not from a read-back.
- Whether a `settings.json` `maxEffortLevel` clamps silently. The
  capability tables above make the model-side clamp certain; the
  settings-side cap was not exercised.
