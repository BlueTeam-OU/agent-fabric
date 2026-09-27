# ADR-007 — A flagged request is contagious

**Date:** 2026-09-16
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #51 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the CEO (named the problem, 2026-09-16); implemented by fabric-coordinator
**Scope:** runtime/claude-code/hooks/model-fallback-note.sh and its wiring (the workspace template, each project's .claude/settings.json); communication/gzcoord/scripts/send.mjs; bin/fabric-status; the gzcoord-send and gzcoord-receive skills
**Pillar:** P1

## 1. Context and Problem

Fable and Opus 5 run with safety classifiers that most often flag
cybersecurity and biology content (code.claude.com/docs: hooks,
model-config; read 2026-09-16). When one flags a request and the category
has a fallback model, the harness re-runs the request there, shows
"…safeguards flagged this message. Switched to …", and the session **stays
on the fallback model until `/model`**. PreModelSwitch does not run for a
switch the harness makes itself; PostModelSwitch does, with `source:
"auto"` and `requested_model: null`, and what that hook prints reaches the
model with the next request. The transcript records the event as a
`model_refusal_fallback` system line with both model ids and the category.
`switchModelsOnFlag: false` in settings turns the switch into a pause with
a choice.

A finding that tripped one session's safeguards trips every session it is
sent to, and a broadcast lands in all of them at once; each then falls
back too. The CEO named this on 2026-09-16 after seeing the notice: the
first agent has to be told, or the finding spreads.

## 2. Decision

A session whose request was flagged is no longer only a session on another
tier: it holds text that will flag every session it reaches, and the
fabric tells it so at the moment it happens. From then on it sends a
finding by **locator and class of problem, never its content**.

## 3. Alternatives Considered

- **A content check on outgoing messages.** Rejected: nothing can tell
  flagged text from any other; only the session can. `send.mjs` therefore
  carries a reminder, never a filter.
- `switchModelsOnFlag: false` is the harness's own alternative (a pause
  with a choice); the sources do not record it being adopted or refused.

## 4. Rationale

The cost of the fallback itself is a tier; the cost of spreading the text
is every recipient's session falling back as well. Telling the sender at
the switch, and the reader at delivery, stops the spread at both ends
without anyone having to judge content they cannot see.

## 5. Binding Rules

1. `model-fallback-note.sh` runs on `PostModelSwitch` with `source:
   "auto"` and tells the session, as context for its next request: that it
   fell back, from which model to which, that the switch is sticky, the
   flagged category (from the transcript's `model_refusal_fallback` line),
   that it now filters anything readable as that category out of
   everything it sends — GZCoord messages, commit messages, PR bodies,
   memories — and that its next report says so.
2. The hook leaves a marker per harness pid under
   `~/.cache/agent-fabric/fallback/`, swept like the plan-hold markers;
   while it is live, `send.mjs` repeats the reminder on stderr.
3. `bin/fabric-status` reports the fallback as drift, with the models and
   the time.
4. Writer's rule (`gzcoord-send`, beside "never a secret value"): after a
   flag, a finding is named by where it is and what class of problem it
   is, never by its content. Reader's rule (`gzcoord-receive`): a delivery
   that flags your session is answered by locator, quoting nothing.
5. The workspace template carries the hook; a session started inside a
   clone takes its hooks from the clone's settings, so each project's
   `.claude/settings.json` adds the `PostModelSwitch` group
   (`projects/gzapp/integration/gzcoord/INSTALL.md`).

## 6. Consequences

- A flagged finding travels as a pointer; the reader fetches it from the
  artifact, in its own session, knowing what it risks.
- Each managed project must wire the hook into its own settings, or its
  sessions go untold.

## 7. Future Evolution

Not measured: a safeguard flag cannot be provoked on purpose, so the hook
firing with `source: "auto"` rests on the documentation and the recorded
transcript event, not a live read-back. The hook's behaviour on that input
is tested (`runtime/claude-code/hooks/test_model-fallback-note.sh`); the
first real fallback under it is the read-back, and its session's report
should say what it saw.

## 8. Decision Status

Accepted and in force; the live read-back is pending the
first real fallback.

## References

- `runtime/claude-code/hooks/model-fallback-note.sh`,
  `runtime/claude-code/hooks/test_model-fallback-note.sh`,
  `runtime/claude-code/workspace/settings.json`.
- `communication/gzcoord/scripts/send.mjs`; `bin/fabric-status`.
- `communication/gzcoord/skills/gzcoord-send/SKILL.md`,
  `communication/gzcoord/skills/gzcoord-receive/SKILL.md`.
- `projects/gzapp/integration/gzcoord/INSTALL.md`.
- ADR-005 (the models and tiers a fallback moves between).
