# ADR-005 — Models are routed by capability class

**Date:** 2026-09-13
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #51 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner (the routing moves of 2026-09-13, 2026-09-19, 2026-09-24, 2026-09-25 and 2026-09-29); architect-cto (the review model, 2026-09-13 and 2026-09-15); landed by fabric-coordinator
**Scope:** routing/capabilities.json, routing/profiles.json, routing/shims.json and routing/shims/, routing/policies/review-grade.json, runtime/claude-code/aliases.json, runtime/openrouter/launch, runtime/claude-code/install-agent-files.sh, runtime/claude-code/hooks/agent-dispatch-guard.sh and model-switch-guard.sh, bin/fabric-model, tools/fabric/routing.py, tools/fabric/shim.py
**Pillar:** P1
**Evidence:** docs/live-checks/2026-09-13-openrouter-routing.md, docs/live-checks/2026-09-14-deepseek.md, docs/live-checks/2026-09-16-openrouter-presets.md, docs/live-checks/2026-09-19-deepseek-top-tier.md, docs/live-checks/2026-09-23-opus-5-5.md, docs/live-checks/2026-09-29-sonnet-5-5.md

## 1. Context and Problem

Agents run on two launch paths — plain `claude` (Anthropic) and the
OpenRouter broker (`ori claude`) — which speak different model
vocabularies, and the model that best serves a kind of work changes every
few weeks. An agent's instructions that named a vendor model would have to
be rewritten at each change; a harness left to pick would re-tune the fleet
on the vendor's schedule.

Three measurements shaped the mechanism. The Agent tool's `model` field
accepts only the four tier aliases (`haiku`, `sonnet`, `opus`, `fable`),
never a full id (2026-09-13). A reviewer dispatched on `opus` was served as
`z-ai/glm-5.3` — code-high's export — because one alias carries one export
per launch (2026-09-13). A model family can need a compatibility shim to
speak the harness's wire protocol, and some members of a family fail it
outright: DeepSeek V4 Flash invented user turns at ~25k context on three
runs, V4 Pro held on a six-step check (2026-09-14).

The mapping has moved since without an agent being rebuilt: on the
broker the session (from Sonnet 5) and the upper classes (from GLM) went
to DeepSeek V4 Pro (2026-09-19); on plain claude every class went from the top model of
its own tier (Haiku 4.5, Sonnet 5, Opus 5.5, Fable 5.1) to Opus 5.5
(2026-09-25), and the two lower classes on from Opus 5.5 to Sonnet 5.5
(2026-09-29).

## 2. Decision

**A task names a capability class; routing decides the model.** Five
classes — `code-low`, `code-medium`, `code-high`, `code-plan` and the
review class `code-review` — are the whole vocabulary in
`routing/capabilities.json`, every profile layer and `bin/fabric-model`.
The file maps each class to a concrete model **per provider**; the layers
of `routing/profiles.json` (defaults ← role ← agent login ← the agent's
own `model-profile.local.json`) override it, each per provider. Which tier
alias a class rides is the Claude Code adapter's
(`runtime/claude-code/aliases.json`); the launcher exports each coding
class's model under that alias's `ANTHROPIC_DEFAULT_*_MODEL`. The review
class shares `fable` with `code-plan`, is never an export, and gets its
model through its agent file; that model is gated by
`routing/policies/review-grade.json`. A family's shim (`routing/shims.json`)
is a separate dimension, and the composite `model@preset/slug` exists only
in the child's environment.

The current mapping:

- **Plain claude.** `code-low` and `code-medium` are
  `claude-sonnet-5-5`; `code-high`, `code-plan` and the review class are
  `claude-opus-5-5`, and so is the default session (A 2026-09-29);
  `architect-cto-01`'s session is `claude-fable-5-1` (an agent layer).
  `anthropic/claude-opus-5-5` is admitted to review-grade without the
  `[1m]` marker (Opus 5.5's context is natively 1M). The aliases stay:
  they are how the harness spells a class; `haiku` and `sonnet` bind to
  Sonnet 5.5, `opus` and `fable` to Opus 5.5.
- **The broker.** The session, `code-high`, `code-plan` and the review
  class are `deepseek/deepseek-v4-pro-0813`; `code-low` and `code-medium`
  are GLM. The reason for the review class is the tier, not the family:
  the owner runs adversarial local review and wants the reviewer on the
  strongest admissible broker model, so its independence is the blind
  brief and a fresh context.
- **Review-grade** admits `z-ai/glm-5.3`, Opus 5, V4 Pro and Opus 5.5;
  V4 Flash stays refused.
- `code-plan` rides `fable`, the top reasoning tier, beside the review
  class; the review model reaches the reviewer by the agent-file route.

## 3. Alternatives Considered

- **A full model id in each agent file, named at dispatch.** Tried first:
  the Agent tool rejects it, the guard denied the unset
  model, the session fell back to `opus` and the reviewer ran on GLM.
- **The review model as the `fable` export.** Rejected once `code-plan`
  rode `fable`: through one export the reviewer would follow `code-plan`,
  as it once followed `code-high` on `opus`.
- **Leaving plain claude to the harness's aliases.** Rejected: the fabric
  would not decide the model on that path; the anthropic column exists so
  it does.
- **A different family for the reviewer as its independence.** Not taken:
  the reviewer's independence is the blind brief
  and a fresh context.

## 4. Rationale

The class is what endures; the model is what changes (ADR-000, P1). Every
class moved to a new model family — GLM to DeepSeek on the broker, the
tier tops to Opus 5.5 on plain claude — by a routing change and a
read-back, without one agent being rebuilt. Gating the reviewer's model in
a closed set keeps an unreviewed model from reaching review through a
profile layer or a local override.

## 5. Binding Rules

1. Instructions, subagent dispatches and agent files name a class, never
   a vendor model; `subagent_type` is the class and `model` its alias from
   `runtime/claude-code/aliases.json`.
2. The dispatch guard (`runtime/claude-code/hooks/agent-dispatch-guard.sh`)
   refuses a class dispatch whose `model` is not its alias, unset
   included; a review on anything but `fable`; and a writing dispatch
   without worktree isolation. `code-high` and `code-plan` ask. A guard
   that infers the alias instead of checking it is not this design.
3. The read-only harness types (`Explore`, `Plan`, `claude-code-guide`)
   name a model and no isolation.
4. Every profile layer is per provider; a choice for one provider never
   reaches the other. `agents` is keyed by the Linux login.
5. The review class's model reaches `~/.claude/agents/code-review.md`
   (`install-agent-files.sh --provider <p>`, before every exec), never an
   export; the guard drops the dispatch's alias so the file decides, and
   denies the review when the file disagrees with the launch's resolution.
6. The review model is a member of `routing/policies/review-grade.json`;
   `tools/fabric/lint.py` refuses a committed profile outside it and the
   launcher refuses the merged result at launch. The reviewer's model is
   chosen there deliberately — architect-cto's call by charter, the
   owner's word above it — and landed by fabric-coordinator, never by a
   profile layer alone; a model or preset is added only after a live test
   showed the harness forwards the reference verbatim.
7. No committed settings scope carries a model pin
   (`policies/check_repo_settings_carry_no_model_pins.sh`); the launcher
   refuses a pin in any settings scope, a caller's
   `CLAUDE_CODE_SUBAGENT_MODEL`, and `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`
   outright.
8. A family gets a shim only after a live test: its source in
   `routing/shims/<slug>/`, pushed and read back with `tools/fabric/shim.py`,
   checked with `shim.py check`, reported in `docs/live-checks/`, then the
   `shims.json` entry by hand. `routing.py check` fails an entry with no
   source.
9. Under a fabric launch, `/model <bare id>` for a family with a shim is
   refused by `model-switch-guard.sh`, which names the composite instead.
10. A model moves into routing only after it is read back served through
    the launcher, with a control showing the pass is not a fallback
    (`2026-09-23-opus-5-5.md`).

## 6. Consequences

- `fabric-model list` shows every choice with its layer; `fabric-status`
  the resolution a session launched with.
- On plain claude every class asks one level today, and the two lower
  classes differ from the upper by model (Sonnet 5.5 against Opus 5.5);
  otherwise the classes differ by alias, isolation and whether a
  dispatch asks (ADR-006). The review shares code-high's model there, so
  its independence is its brief and context.
- Nothing validates a model id against a catalogue: a typo is caught by
  the adapter's shape check and the launch read-back, not by routing.

## 7. Future Evolution

The broker-path agent-file route for the review class (a composite in the
file) is not yet read back live. A new model family is expected to arrive
by a routing change and a measured read-back and nothing else (ADR-000
P1's direction).

## 8. Decision Status

Accepted; the current mapping is the one §2 states, on both paths.

## References

- `routing/capabilities.json`, `routing/profiles.json`, `routing/shims.json`,
  `routing/policies/review-grade.json`, `runtime/claude-code/aliases.json`.
- `runtime/openrouter/README.md` (the two paths, the three steps, the
  invariant), `runtime/openrouter/launch`, `bin/fabric-model`,
  `tools/fabric/routing.py`, `tools/fabric/shim.py`.
- `runtime/claude-code/hooks/agent-dispatch-guard.sh`,
  `runtime/claude-code/hooks/model-switch-guard.sh`,
  `runtime/claude-code/install-agent-files.sh`,
  `policies/subagent-dispatch/SKILL.md`.
- The six live checks in Evidence. ADR-002 (the dimensions).

## Amendments

The body above reads current; each change's full note is in [history/ADR-005-amendments.md](history/ADR-005-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-09-29 | code-low and code-medium are Sonnet 5.5 on plain claude | §2 the current mapping: the two lower classes on `claude-sonnet-5-5` |
