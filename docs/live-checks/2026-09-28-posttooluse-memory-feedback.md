# A PostToolUse hook on Write: the path it gets, and whether the model reads its feedback (2026-09-28)

What was measured, on develop-qzapp as user, Claude Code 2.1.282, before
building the memory-write check (`runtime/claude-code/hooks/memory-write-check.py`).

## The probe

A throwaway settings layer (`claude -p --settings <file>`) wired one
PostToolUse hook, matcher `Write|Edit`, whose command saved its stdin and
printed:

```json
{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"MEMORY-CHECK-7Q: the memory you wrote has no roles_class."}}
```

The prompt asked the session, on Haiku, to write one file with the Write
tool and then to reply with exactly the text of any message a hook had
given it, or `NONE`.

## What came back

- The session's reply was the marker line, word for word: a PostToolUse
  hook's `additionalContext` reaches the model in the same turn.
- The saved payload: `hook_event_name` `PostToolUse`, `tool_name`
  `Write`, and `tool_input.file_path` the absolute path written. The keys
  were `cwd`, `duration_ms`, `effort`, `hook_event_name`,
  `permission_mode`, `prompt_id`, `session_id`, `tool_input`,
  `tool_name`, `tool_response`, `tool_use_id`, `transcript_path`.

## Cost

The check itself, timed over seven memory files and two other paths:
about 40 ms for a path it ignores, 80–130 ms for a memory it judges
(two module imports and one file read). Nothing is written.

## What it decides

The check runs as a PostToolUse `Write|Edit` hook and answers through
`additionalContext`, one line per problem, silent otherwise. It is
wired at user scope by the settings writer, not in the workspace
template: a memory belongs to the account wherever the session started,
and a template hook would ask every managed project to mirror it
(ADR-022 rule 9).
