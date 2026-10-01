---
role: "fabric-coordinator"
class: solution
topic: "effort-precedence-chain"
description: How Claude Code resolves reasoning effort, read out of the 2.1.280 binary — the order, the escape values, and where each level can be read back
tier: 2
knowledge_scope: full
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - bc16158317197271
---

## How Claude Code resolves reasoning effort, read out of the 2.1.280 binary — the order, the escape values, and where each level can be read back

Deminified from `~/.local/share/claude/versions/2.1.280`. The resolver is
`aS(model, configured, {turnEffort, hookEffortValue})`, highest first:

1. `hookEffortValue` — **internal retry plumbing, not a hook**. Its only
   caller compares a retry's effort with what was sent
   (`r.effort !== e.sent.effort`). No hook event can set effort.
2. `CLAUDE_CODE_EFFORT_LEVEL` (`ZD()`) — the highest thing a human sets.
3. `turnEffort` — `--effort` / `/effort`.
4. `configured` — an agent file's `effort:`, the session's level.
5. the model's own `default_effort`, else `"high"`.

**`unset` and `auto` are VALUES, not absence.** `ZD()` maps either
(case-insensitive) to `null`, and `null` means *skip the configured level
and use the model's default* — so `CLAUDE_CODE_EFFORT_LEVEL=auto` in a
shell profile silently defeats every per-class level, rather than
disabling the variable.

**The clamp is per-model and only downward from the top:**
`max -> high` when the model lacks `max_effort`, `xhigh -> high` when it
lacks `xhigh_effort`. Lower levels pass through untouched. Canonical
scale: `["low","medium","high","xhigh","max"]` — five, no `none`, no
`minimal`.

**The bundled model registry** is the authority for what a model admits:
each entry carries `capabilities` (with `effort`, `max_effort`,
`xhigh_effort` as three separate entries) and `default_effort`. A model
without `effort` is gated out by `L_()` before a request is built, so no
level is ever sent for it — narrower than "rejects the parameter".
Extract with `first_party:"claude-…"` plus the following
`capabilities:[…]`; a `fallback_3p` in the same entry names the PREVIOUS
model, so keying on it shifts the whole table by one.

**`/effort` persists `modelSettings.<model>.effortLevel` into
`~/.claude/settings.json`.** Any fence that refuses `modelSettings` in a
user scope blocks every account that has ever used the command — and it
cannot defeat `--effort` anyway, which sits above the configured slot.
`maxEffortLevel` is the one that can: it is a cap and the *lowest* value
across scopes wins.

**A subagent's effort IS readable — from its transcript**, not its
environment. Every entry of `subagents/agent-<id>.jsonl` carries
`"effort": "<level>"` (absent for a model with no effort capability).
Proven with the channel isolated: agent file `medium`, parent session
`high`, subagent recorded `medium`. `CLAUDE_EFFORT` is the session's only.
I first concluded the opposite from one control on Haiku — the one model
that has nothing to record. A null result from a sample that could not
show the effect is not a negative: pick the control that CAN show it.

See [[opus-5-5-default-effort-drop]] and
`docs/live-checks/2026-09-23-effort-registry.md`.

*References: opus-5-5-default-effort-drop*

*Observed 2026-09-23 (fabric-coordinator)*
