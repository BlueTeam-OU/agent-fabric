# runtime/openrouter — the broker launch path

How a Claude Code session starts through OpenRouter, and which model each
capability class gets there. One decision per launch: the provider chosen
at launch applies to everything under the session, subagents included.

| | unlaunched vanilla (`claude`) | fabric vanilla (`launch --provider anthropic`) | broker (`launch`) |
|---|---|---|---|
| provider | Anthropic, by construction | Anthropic, plain `claude` | OpenRouter (`ori claude`) |
| who launches | the Linux login (`runtime/identity.py`) | the same login; the role comes from its binding | same |
| session model | harness default | `providers.anthropic.session` from the profile layers — a native id, or a class (that class's model here); a flat `anthropic/<id>` session serves too, `anthropic/` dropped; another vendor's id is refused | `providers.openrouter.session` / flat `session` — an OpenRouter id, or a class (+ family shim) |
| capability classes | harness aliases (`haiku`/`sonnet`/`opus`/`fable`), whatever the harness binds them to this week | the `anthropic` column of `routing/capabilities.json`, overridden per class by the layers: Opus 5.5 for every class (the owner, 2026-09-25; until then the top model of each class's tier — Haiku 4.5, Sonnet 5, Opus 5.5, Fable 5.1), each exported as `ANTHROPIC_DEFAULT_<ALIAS>_MODEL` for the tier the class rides (`runtime/claude-code/aliases.json`, the adapter's); a null in the column leaves that tier to the harness | the `openrouter` column, overridden per class by the layers → model → `routing/shims.json` → the same exports |
| review class (`code-review`) | the `fable` alias, the harness's | pinned: `claude-opus-5-5` (the column, or `providers.anthropic.capabilities.code-review`), written into `~/.claude/agents/code-review.md` at launch; the dispatch checks `model: fable` and then hands the model to the file (architect-cto, 2026-09-15; `claude-opus-5[1m]` until 2026-09-25); never the `fable` export, which is `code-plan`'s; gated by review-grade | the same route with the composite: `z-ai/glm-5.3@preset/…` in the file, gated by review-grade |
| per-role / per-agent choice | none | `routing/profiles.json` layers + the agent's `model-profile.local.json`, the `providers.anthropic` part: the session and the five classes, as native ids — `bin/fabric-model set --provider anthropic …` | the same layers, the `providers.openrouter` part: the session and the five classes, as OpenRouter ids — `bin/fabric-model set --provider openrouter …` |
| review-grade floor | none — the harness's Fable tier | `routing/policies/review-grade.json`, checked at launch | same |
| refusals | none | no bound role, model pins in any settings scope, an ungraded review pin, a non-Anthropic session, no long-lived Claude sign-in (docs/claude-accounts.md), a `.claude.json` whose onboarding cannot be marked | the same, plus `ori` not authenticated from the environment |
| how to inspect | `bin/fabric-status` says "not launched by the fabric" | `bin/fabric-status` says "launched by the fabric" with the pins; `AGENT_FABRIC_LAUNCH_PROVIDER=anthropic` | same, plus `ori auth --json` |

**The class is the vocabulary; the alias is the adapter's.** Five
capability classes — `code-low`, `code-medium`, `code-high`, `code-plan`,
`code-review` — are what `routing/capabilities.json`, every profile layer
and `bin/fabric-model` speak. Which harness tier alias a class rides
(`code-plan` → `fable`, `code-high` → `opus`, …) is
`runtime/claude-code/aliases.json`, internal to the Claude Code adapter:
it decides the `ANTHROPIC_DEFAULT_*_MODEL` variable a class is exported
under and the `model:` a dispatch must say, nothing a user configures.

**Every layer is per provider.** The two paths speak different model
vocabularies — an OpenRouter id on the broker; a native `claude-…` id on
plain claude — so a layer names each provider's choices under
`providers.<provider>` and a choice made for one never reaches the other
(a GLM session on the broker says nothing about plain claude). The
repository holds the general default per provider (`routing/profiles.json`
`defaults`, over the column in `routing/capabilities.json`); the agent's
own layer is `$STATE_DIR/model-profile.local.json`, which `bin/fabric-model`
lists, sets, unsets and seeds — `list` shows every choice with the layer it
came from, `seed` copies the merged defaults in as explicit pins:

```sh
bin/fabric-model list --provider anthropic
bin/fabric-model set --provider anthropic session code-plan               # the session on a class's model
bin/fabric-model set --provider anthropic code-high claude-opus-5[1m]      # exported for the tier it rides
bin/fabric-model set --provider anthropic code-review claude-opus-5        # the reviewer's file
bin/fabric-model set --provider openrouter code-medium z-ai/glm-5.3
```

**The middle column exists so that the fabric decides every class's
model on the vanilla path too**: the column pins the top of each tier and
the launcher exports it. **The review class shares its tier with
`code-plan` and is never an export**: one alias carries one export, so
through `ANTHROPIC_DEFAULT_FABLE_MODEL` the reviewer would follow
`code-plan` — exactly how it once followed `code-high` on `opus`
(2026-09-13). Its model reaches `~/.claude/agents/code-review.md`
instead, on both paths: the launcher runs
`runtime/claude-code/install-agent-files.sh --provider <p>` before every
exec (the native pin on plain claude, the composite on the broker), the
dispatch guard checks `model: fable` and then drops it so the file
decides, and denies the review when the file disagrees with the launch's
own resolution (another launch of the account on the other provider has
rewritten it). The file route is verified live on plain claude
(2026-09-15: the Agent tool's `model` accepts only the four aliases — a
hook rewriting it to a native id is rejected at schema validation; the
dispatch's `model` outranks the agent file's; an agent file whose
frontmatter names a native id runs on it when the dispatch leaves `model`
unset; read-back session `7052df73`, main on `claude-sonnet-5`, the
review subagent on `claude-opus-5`). On the broker the same file carries
a composite `model@preset/…` the way `--model` does for the session; that
leg is not yet read back live.

## The three steps, and where each lives

```text
capability class  --routing/capabilities.json-->  concrete model
concrete model    --routing/shims.json-------->  family shim (or none)
model + shim      --tools/fabric/routing.py--->  model@preset/slug   (runtime only)
```

Today's OpenRouter policy resolves to:

```text
code-low     z-ai/glm-5.3-flash  + @preset/glm2claude-shim  -> ANTHROPIC_DEFAULT_HAIKU_MODEL
code-medium  z-ai/glm-5.2        + @preset/glm2claude-shim  -> ANTHROPIC_DEFAULT_SONNET_MODEL
code-high    deepseek/deepseek-v4-pro-0813  + @preset/deepseek2claude-shim  -> ANTHROPIC_DEFAULT_OPUS_MODEL
code-plan    deepseek/deepseek-v4-pro-0813  + @preset/deepseek2claude-shim  -> ANTHROPIC_DEFAULT_FABLE_MODEL
code-review  deepseek/deepseek-v4-pro-0813  + @preset/deepseek2claude-shim  -> ~/.claude/agents/code-review.md  (review-grade.json admits it; GLM 5.3 and Opus 5 stay admitted)
session      deepseek/deepseek-v4-pro-0813  + @preset/deepseek2claude-shim  -> --model  (routing/profiles.json defaults; a local layer overrides it)
```

Effort rides the same resolution, in its own file (`routing/effort.json`)
and out through a different channel. EVERY class's agent file carries an
`effort:` line, not only the review class's `model:` — the Agent tool has
no per-dispatch effort, so the file is the only per-class channel there
is. A class whose model admits no effort gets no line, which is not the
same as a default. The session's level rides `--effort` and is stamped as
`AGENT_FABRIC_LAUNCH_EFFORT`; agent-fabric ADR-006 is the decision (`docs/adr/ADR-006-effort-is-routed.md`).

```text
code-low     low    -> ~/.claude/agents/code-low.md      (asked medium; GLM 5.3 Flash has no medium, so low — the committed acknowledgement)
code-medium  high   -> ~/.claude/agents/code-medium.md   (asked medium; GLM 5.2 remaps it up)
code-high    high   -> ~/.claude/agents/code-high.md     (asked medium; DeepSeek V4 Pro remaps it up)
code-plan    high   -> ~/.claude/agents/code-plan.md     (asked medium; the same)
code-review  high   -> ~/.claude/agents/code-review.md   (asked medium; the same)
session      high   -> --effort                          (routing/effort.json `session`: medium; DeepSeek serves high)
```

A shim is an OpenRouter preset whose text and routing config live in
`routing/shims/<slug>/` and move to and from the account with
`tools/fabric/shim.py` (`pull`, `diff`, `push`); a candidate family is
admitted by `shim.py check <model> --shim <slug>`, the six-step
compatibility task read back per generation
(`docs/live-checks/2026-09-16-openrouter-presets.md`). Only the Z.ai/GLM
and DeepSeek V4 families have a shim. A model of any other family gets none
(`tools/fabric/routing.py table` shows it). Do not add a family until a live
test has shown it works.

## The invariant

**Canonical files hold classes, models and shims separately; the composite
exists only in the child's environment.** No committed settings scope may
carry a model pin (`policies/check_repo_settings_carry_no_model_pins.sh`),
and the launcher refuses to run when any settings scope — user, user-local,
`$CLAUDE_CONFIG_DIR`, the launch working copy's, or the gitignored local one
the guard cannot see — or the caller's `CLAUDE_CODE_SUBAGENT_MODEL` would
race its pins. `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` is refused outright: it
discards every dispatch's own model, and capability classes would stop
meaning anything.

The main agent's GLM compatibility is the same shim applied to the
`session` model and passed as `--model` — separate from, and unaffected by,
how the capability classes resolve.

**A hand `/model` inside the session cannot drop the shim.** The launch
binds a family to its shim once, in the child's environment; `/model
<bare id>` afterwards would run that family with none, and what follows
reads as a model defect rather than a routing one. The `PreModelSwitch`
hook `runtime/claude-code/hooks/model-switch-guard.sh` — armed only when
`AGENT_FABRIC_LAUNCH_PROFILE` is set, so a vanilla `claude` never sees
it — refuses a bare target whose family `routing/shims.json` gives a shim
and names the composite to switch to instead; a composite, a tier alias
(the launcher's own export) and a family with no shim pass. It asks
`tools/fabric/routing.py shim <model>` rather than matching families
itself, so a family added to `shims.json` is guarded from that moment
with nothing else to update.

## Who is launching

The agent is the Linux login; the launcher asks `runtime/identity.py` and
reads the role from that agent's runtime binding (written from a login
shell by `bin/fabric-role`), renders it into the session's system prompt
(`tools/fabric/launch_prompt.py`, passed as `--append-system-prompt-file`;
a caller's own `--system-prompt*` is refused) and stamps it
(`AGENT_FABRIC_LAUNCH_ROLE`, `_PROMPT_DIGEST`). It announces nothing:
presence is the control plane's (`docs/adr/ADR-030-presence-replaces-hello-and-goodbye.md`). The session is a
child the launcher waits on, not an exec, so it can bring the session
back after an upgrade or an account move. The launch
directory decides which settings scopes are fenced and which working copy
the child starts in. It never decides who the agent is: `test_launch.sh`
launches from a directory named for another agent with `USER` forged and
checks the label still reads this login.

The prompt file carries the ROLE layer only — the identity header, the
charter, the brief, the shared team and memory sections
(`identities/prompt/`). The project layer (the remit, the INDEX pointer)
follows the working copy and reaches the session from the SessionStart
hook, not from this file; `docs/adr/ADR-002-role-login-and-model-are-kept-apart.md` has
the whole account, and `docs/live-checks/2026-09-15-append-system-prompt.md`
the read-backs. A session's role is fixed at exec: a rebind from the shell
under it is reported as DRIFT by `bin/fabric-status`, never applied.

## Files

- `launch` — the launcher. `--print` resolves without spawning — it is the
  launcher's flag, not claude's: for a headless run use claude's short
  form, `-p "prompt"`, which passes through.
- `model-audit.sh` — what is the current session actually routed through,
  and how to read back the served model.
- `test_launch.sh` — the behavioural suite for the launcher and the audit
  (`bash policies/run_suite.sh runtime/openrouter/test_launch.sh`).

## Why every class rides an alias, and how the review class got its own model (verified live 2026-09-13; read-backs in `docs/live-checks/2026-09-13-openrouter-routing.md`)

The Agent tool's `model` field accepts **only the four tier aliases**
(`haiku`, `sonnet`, `opus`, `fable`); a full id such as `claude-opus-5[1m]`
is rejected as an invalid parameter. So a class cannot be "declared" by
full id in its agent file and named at dispatch — the first design tried
exactly that, the dispatch guard refused the unset model, the session fell
back to `opus`, and OpenRouter's `/generation` record showed the reviewer
served as `z-ai/glm-5.3` (Modal, GLM preset applied): code-high's export.

Every class therefore rides an alias, and one alias carries one export.
The 2026-09-13 binding gave the review class `fable`, then the alias no
coding class used, and exported the review model under
`ANTHROPIC_DEFAULT_FABLE_MODEL`. Since `code-plan` (2026-09-15) rides
`fable` as the top reasoning tier, the review class keeps the alias for
the dispatch's `model:` check and takes the agent-file route for its
model (above), on both paths; the review gate guards that file's model
exactly as it guarded the export.

Which model the reviewer runs on is `routing/capabilities.json` (or a
profile layer), gated by `routing/policies/review-grade.json`. The
read-back on the 2026-09-13 binding
(a `model: fable` reviewer from a GLM 5.3 session served as
`anthropic/claude-opus-5` on every generation) proved the export is the
reviewer's own; architect-cto then admitted `z-ai/glm-5.3` to
review-grade and made it the broker review model (2026-09-13); on
2026-09-19 the broker's review model moved to DeepSeek V4 Pro with its
shim (the owner; agent-fabric ADR-005), and GLM 5.3 and Opus 5 remain
admitted choices for a profile that wants them. The separation still
matters: review and code-high can be given different models, and the
review model can be raised without touching the coding classes.

Also verified the same day: `ori` forwards an unprefixed Anthropic id
untouched (`--model claude-opus-5[1m]` was served as
`anthropic/claude-opus-5-20260723` by "Claude Platform on AWS"), so the
composite in the fable export needs no vendor rewriting. `ori` prints
"not in the OpenRouter catalog, passing it through untouched" for that id
and for every `@preset/` composite; the public catalog lists neither
form, and the warning is cosmetic.
