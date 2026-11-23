# Can a PreToolUse hook rewrite a reviewer's Bash command?

#96's nine review rounds kept finding spellings that the review class's
Bash fence did not know, all of them in one class: bash expanding a path,
or an allowed tool running a program the guard never sees. A string
match cannot follow either. What closes the environment half of that
class is a review session that does not have the secrets in the first
place: each command it runs starts from a clean environment. That needs
the fence to change a command, not only refuse one. Claude Code's
`PreToolUse` hook output has an `updatedInput` field for that. Before
building on it, three questions were measured on develop-qzapp, as the
account `user`, with Claude Code 2.1.285 (the fleet's pin), in
`claude -p` runs from a scratch directory, each with a probe hook that
returned a fixed command in place of the one asked for.

## Does `updatedInput` replace the command?

The hook answered with `permissionDecision: allow` and `updatedInput:
{command: "echo REWRITTEN-BY-HOOK"}`, and the session was asked to run
`echo original-command`. It reported `REWRITTEN-BY-HOOK`. The command
that ran was the hook's.

## Does it need a permission decision?

A fence that answered `allow` for every command it lets through would
skip the session's own permission checks for each of them. So the hook
was run twice more:

- **No `permissionDecision`, only `updatedInput`:** the session reported
  `REWRITTEN-NO-DECISION`. The rewrite applies, and the call goes on
  through the session's normal permission flow (here `--allowedTools
  Bash` let it run).
- **`permissionDecision: ask` with `updatedInput`:** the call stopped for
  confirmation, which a non-interactive run cannot give, so nothing ran.

A rewrite with no decision is the shape a fence needs: it changes what
runs and nothing about who may run it.

## Does it work from a subagent's frontmatter hook?

The review class's fence is a hook in the code-review agent's
frontmatter. A probe agent with the same frontmatter shape was written
to a scratch project's `.claude/agents/`; dispatched from `claude -p`
there, its hook never fired (a marker file it writes stayed absent). The
same agent written user-scope, to `~/.claude/agents/`, where the fleet's
agent files live, did: the hook received `agent_type: zz-probe-runner`,
`hook_event_name: PreToolUse` and `tool_name: Bash`, answered with only
`updatedInput`, and the subagent reported `REWRITTEN-IN-SUBAGENT`. The
probe agent file was removed after each run.

## What it decides

- The fence rewrites every command it allows into
  `env -i NAME="$NAME" … bash -c '<the command>'`, naming only
  variables that carry no secret, and answers with no permission
  decision. The values are expanded by the reviewer's own shell when the
  command runs; the hook never sees them.
- The project-scope miss is the probe's setting, an untrusted scratch
  directory under `-p`, not the fleet's: the fleet installs the
  code-review agent user-scope, as measured here.
- `updatedInput` is the documented hook output; a later Claude Code that
  dropped it would run the original command, which the string fence
  still judges. No suite would see that: the oracle runs the rewrite
  itself, outside Claude Code. What catches it is a read-back after a
  Claude Code upgrade: a reviewer running
  `python3 tests/fixtures/clean-env-probe.py`, whose names must be
  `CLEAN_ENV`'s and those the shell and Python add themselves (`SHLVL`,
  `_`, `LC_CTYPE`), and no other.
