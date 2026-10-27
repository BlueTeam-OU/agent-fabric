# Live check 2026-09-13 — OpenRouter routing, shim injection, review class

What was actually served, read back from OpenRouter's `/api/v1/generation?id=`
records (the served model is the only ground truth; the harness banner
echoes whatever `--model` it was given). Generation ids are the `message.id`
values in the Claude Code transcripts of the sessions named. Host
`develop-qzapp`, agent `user`, role `architect-cto`, `ori claude` through
`runtime/openrouter/launch`.

## 1. The GLM shim preset is applied, prepended, once

Session launched with `--model z-ai/glm-5.3@preset/glm2claude-shim`.

| generation | served model | provider | preset_id | prompt / cached | note |
|---|---|---|---|---|---|
| `gen-1789308463-BonK0CtdD9MaMJXBMLH1` | `z-ai/glm-5.3-20260816` | Friendli | `d63c6cc2-b74b-4898-9387-177b0906cdc9` | 22 223 / 448 | cold |
| `gen-1789308574-HtIbE9C5lWS0lL1auI3f` | `z-ai/glm-5.3-20260816` | Friendli | same | 22 637 / 16 768 | cache hit 74 % |

`preset_id` is the preset whose slug is `glm2claude-shim` (`/api/v1/presets/glm2claude-shim`:
status `active`, version 1, `config: {}` — system prompt only).

Asked to quote the text around the preset's heading, the model quoted
"# Z.ai GLM → Claude Code compatibility delta" as the very start of its
system prompt, followed by the `x-anthropic-billing-header: cc_version=…`
line and then "You are Claude Code, Anthropic's official CLI for Claude."
So OpenRouter PREPENDS the preset prompt as the first system block, ahead
of Claude Code's own first block, and injects it once (`ori` adds nothing).

`ori` prints "`--model … is not in the OpenRouter catalog, passing it
through untouched`" for every `@preset/` composite: presets are per-account
and never in the public model list. Cosmetic.

## 2. A review dispatched on the `opus` alias ran on GLM (the declared-id design fails)

Same session; `blind-reviewer.md` then declared `model: claude-opus-5[1m]`.
The Agent tool rejected `model: "claude-opus-5[1m]"` as an invalid
parameter (the field accepts only `sonnet|opus|haiku|fable`); the dispatch
guard denied the unset model; the session retried with `opus`.

| generation | served model | provider | preset_id |
|---|---|---|---|
| `gen-1789309652-zz5ZPKFFh5MA2A22YYwn` | `z-ai/glm-5.3-20260816` | Modal | glm2claude-shim |
| `gen-1789309654-JFCP0ElTy2ewFBk1V2HA` | `z-ai/glm-5.3-20260816` | Modal | glm2claude-shim |

The reviewer was code-high's export. This is why the review class now rides
`fable` (`runtime/openrouter/README.md`).

## 3. `ori` forwards an unprefixed Anthropic id untouched

`runtime/openrouter/launch --model 'claude-opus-5[1m]' -p 'Reply with the single word OK.'`

| generation | served model | provider | preset_id | cost |
|---|---|---|---|---|
| `gen-1789309741-Sngj2TiNHjdnlMEUR5Ji` | `anthropic/claude-opus-5-20260723` | Claude Platform on AWS | none | $0.1217 |

Since j417 (2026-10-27) the launcher refuses an unprefixed native id on the broker; use `anthropic/claude-…`.

## 4. A review dispatched on the `fable` alias is the reviewer's own export

Session on `z-ai/glm-5.3@preset/glm2claude-shim`; launcher exported
`ANTHROPIC_DEFAULT_FABLE_MODEL=anthropic/claude-opus-5[1m]`; dispatch
`blind-reviewer`, `model: "fable"`, no isolation.

| generation | served model | provider | preset_id | prompt / cached |
|---|---|---|---|---|
| `gen-1789310379-uLPrPuSPthzB7t7dInLc` | `anthropic/claude-opus-5-20260723` | Claude Platform on AWS | none | 7 244 / 0 |
| `gen-1789310383-oqw8r1wlS5HJYcQZZ4J1` | `anthropic/claude-opus-5-20260723` | Claude Platform on AWS | none | — |
| `gen-1789310388-DyWarvkpbaWvegbOrv8V` | `anthropic/claude-opus-5-20260723` | Claude Platform on AWS | none | 10 836 / 7 640 |

The session stayed on GLM; the reviewer got the fable export and nothing
else. After this read-back architect-cto admitted `z-ai/glm-5.3` to
`routing/policies/review-grade.json` and made it the broker review model;
the mechanism is unchanged.

## 5. The shim applies to every family member the profiles use

Headless `runtime/openrouter/launch --model <model>@preset/glm2claude-shim -p
'Quote verbatim the first heading of your system prompt, then reply with the
single word OK.'` — each answered "# Z.ai GLM → Claude Code compatibility
delta" then "OK".

| model | generation | served model | provider | preset_id | cost |
|---|---|---|---|---|---|
| `z-ai/glm-5.2` | `gen-1789311118-HXnfHZlZh3nZVPudjlQN` | `z-ai/glm-5.2-20260616` | Together | glm2claude-shim | $0.0279 |
| `z-ai/glm-5.3-flash` | `gen-1789311125-5TAKmt2arP4aP7tLpKxZ` | `z-ai/glm-5.3-flash-20260826` | Wafer | glm2claude-shim | $0.0020 |

(`z-ai/glm-5.3`: runs 1, 2 and the fable-alias read-back after the
review-model change.) The harness prints `[claude-code:unrecognized_model]`
for the composite in headless mode — a log line, not an error; the request
went through.

## Reviewer's own caveat from run 4

Dispatched from `projects/` (not a working copy), the reviewer's `Bash`
was denied because `review-bash-guard.sh` is looked up under
`$CLAUDE_PROJECT_DIR/.claude/` and only gzapp carries it; it reviewed the
working tree, not the range. Fixed the same day: the guard now lives in
`runtime/claude-code/hooks/`, `bootstrap.sh` installs it at
`~/.claude/hooks/review-bash-guard.sh`, and the agent file falls back to
that path when the launch project has no `.claude/` copy.
