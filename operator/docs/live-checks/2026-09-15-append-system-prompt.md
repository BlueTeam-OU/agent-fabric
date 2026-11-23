# Live check 2026-09-15 — the role in the system prompt, on both launch paths

What was read back before the launcher gained `--append-system-prompt-file`
(the role-at-launch plan, owner decision of 2026-09-15). Host
`develop-qzapp`, agent `user`, role `fabric-coordinator`, Claude Code
`2.1.272`. Every check appended a one-line file whose only content was a
marker token, then asked the session to quote the line of its system prompt
containing the marker or to answer `NO MARKER`; a control that answered
`NO MARKER` would have shown the flag was accepted and ignored.

## 1. The flag exists, hidden from `--help`

`claude --help` lists `--append-system-prompt <prompt>` and
`--system-prompt <prompt>` only; `--append-system-prompt-file` appears in
the help text solely as the `[-file]` shorthand inside `--bare`'s
description. The argv parser of the installed binary declares
`--append-system-prompt-file <file>`, `--system-prompt-file`,
`--append-subagent-system-prompt-file` and `--system-prompt-snapshot
<on|off>` (strings in `~/.local/share/claude/versions/2.1.272`; the error
text "Cannot use both --append-system-prompt and
--append-system-prompt-file" names the pair). `claude
--append-system-prompt-file /dev/null --version` exits 0, as does an
unknown flag — so the parser check alone proves nothing; the read-backs
below do.

## 2. Plain claude through the launcher, print mode

`runtime/openrouter/launch --provider anthropic --append-system-prompt-file
<marker file> -p '<quote the marker line>'` — the launcher passed the flag
through untouched (it refuses only `--settings`/`--setting-sources`) and
the answer was the marker line verbatim.

## 3. `ori claude` through the launcher, print mode

Same call without `--provider` (the broker; session
`z-ai/glm-5.3@preset/glm2claude-shim`). `ori` printed its usual
"not in the OpenRouter catalog, passing it through untouched" line and the
answer was the marker line verbatim. The broker path forwards the flag and
the shim preset does not displace the appended text.

## 4. Interactive mode, plain claude

`script -qfec "claude --append-system-prompt-file <marker>" /dev/null`
with the keystrokes piped in (accept the workspace-trust dialog, the
question, `/exit`). The rendered transcript carried the marker line twice —
once in the model's answer (`● FABRIC-MARKER-…: this line was appended by
agent-fabric at launch.`) — and `NO MARKER` only in the echoed question.
The first attempt, without accepting the trust dialog, never reached a
turn: a fresh scratch directory prompts for trust before the first prompt,
which matters for any headless read-back but not for the launcher (the
account's `projects/` and clones are already trusted).

## 5. `--system-prompt-snapshot on` beside the file

`claude --append-system-prompt-file <marker> --system-prompt-snapshot on
-p '<answer with the marker id>'` answered `FABRIC-MARKER-7741`, exit 0.
Accepted together; what the snapshot changes at runtime (the prompt
recorded once per conversation and reused verbatim on every request and
resume) was not observed here and is not relied on — the launcher may pass
it, the prompt file is byte-stable regardless.

## 6. A SessionStart hook's JSON `additionalContext` reaches the model

A settings file whose only hook printed
`{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":
"… HOOK-MARKER-5522 …"}}`; `claude --settings <it> -p '<answer with the
HOOK-MARKER token or NONE>'` answered `HOOK-MARKER-5522`. The structured
form is taken, so the session-start hook can carry the project remit that
way (the plan's step 6).

## What this decides

- `runtime/openrouter/launch` passes `--append-system-prompt-file
  "$STATE_DIR/launch-prompt.md"` on all four exec branches (plain and
  `ori`, with and without a caller `--model`); a caller's own
  `--system-prompt*` / `--append-system-prompt*` is refused, as
  `--settings` is.
- The role layer (charter, brief, team and memory guides) goes in that
  file; the project layer (remit, INDEX pointer) goes through the
  session-start hook's `additionalContext`, which follows the cwd.
- `--system-prompt-snapshot on` may ride along; nothing depends on it.
- Not read back: whether the appended text survives `/compact` in place
  (it is part of the system prompt, which is re-sent every request; the
  plan's verification step asks the question after a compaction).
