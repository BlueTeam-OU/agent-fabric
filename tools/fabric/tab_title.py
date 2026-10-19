#!/usr/bin/env python3
"""tools/fabric/tab_title.py — the Claude Code hook that sets the terminal tab title to
<agent> <working-copy>/<branch>, behind runtime/claude-code/hooks/tab-title.sh (Wave 9 batch 7, ADR-040 §7).

Contract, frozen from the shell script and pinned by tests/test_tab_title_cli.py:
  stdin   the hook payload; only `cwd` is read. $PWD stands in for a payload that is no JSON, has no cwd or
          names no directory
  stdout  one line of JSON, {"terminalSequence": "ESC ] 0 ; <title> BEL"}, or nothing when there is no title
          to set (no repository, no branch, no git); nothing on stderr
  exit    0 always: a hook that fails must never block or annotate the tool call it is observing, and a
          non-zero exit surfaces an error notice on EVERY Bash tool call
  writes  nothing

WHY. Several sessions run in parallel, one agent (Linux login) each, and what tells them apart is the agent plus
the working copy and branch it is on. The status line already shows those while you are looking at a pane; this
puts them on the TAB, which is what you read when you are looking at a different pane. The agent comes from
agent-fabric's canonical resolver; the working copy is the checkout's basename — context, never identity.

WHY NOT /rename. That sets the session name, and the session name normally drives the tab title -- but it cannot
be automated. Hooks are shell processes, not conversation turns, so nothing can invoke a slash command, and no
setting, CLI flag or plugin renames a running session. "claude -n <name>" names a session once at startup and
never follows a branch. The Agent SDK does expose a rename call, but it is a separate product appending to the
live session's own transcript from a second process: whether a running session reflects it is undocumented, and
so is racing that session's own writer. So the tab title is driven directly instead, which is the part that was
reachable without betting on any of that.

HOW. A hook cannot write to the terminal itself -- hooks run with no controlling terminal, so an OSC escape
printed to /dev/tty goes nowhere. A hook may instead RETURN a top-level "terminalSequence" field, which the
harness writes through its own terminal path: race-free, and it survives tmux. The allowlist is narrow -- OSC
0/1/2 for titles, 9/99/777 for notifications, and BEL -- and OSC 0 sets both the window and the icon title,
which is what tab bars read. The escapes are JSON's \\u001b and \\u0007 text, so no raw control byte is in this
file, which survives an editor, a diff view or a copy-paste.

NO COMMAND FILTER, deliberately. It would be cheaper to recompute only after a "git checkout" or "git switch",
but a filter only catches branch changes made by a command this session ran AND matched. A script that switches
branches, a rebase, or anything the regex did not anticipate would leave a stale title -- and a stale title is
worse than no title, because it is believed. Two git calls per tool call does not buy that risk.

Wired for SessionStart (set it at launch) and PostToolUse on Bash (which runs after the command, so a branch
change has already happened) in settings.json.
"""
import json
import os
import sys

import git
import hook_common

GIT_TIMEOUT_S = 10


def git_out(directory: str, *args: str) -> str:
    try:
        return git.out(directory, *args, timeout=GIT_TIMEOUT_S)
    except git.GitError:
        return ""


def session_directory(raw: bytes) -> str:
    # The hook payload carries the session's directory; $PWD is the fallback for a manual run or a payload without it.
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = None
    cwd = payload.get("cwd") if isinstance(payload, dict) else None
    return cwd if isinstance(cwd, str) and os.path.isdir(cwd) else os.getcwd()


def main_worktree(directory: str) -> str:
    """THE MAIN WORKTREE, not the current one. Every subagent dispatch runs in a linked worktree under
    .claude/worktrees/ on its own generated branch, so resolving "here" would title the tab
    agent-<id>/worktree-agent-<id> -- 55 characters saying nothing about which clone or which task, which is the
    whole point of the title. Worse, it would persist after the agent finished, until the session happened to
    run a Bash call of its own. --git-common-dir points at the SHARED .git for a linked worktree and at this one
    otherwise, so its parent is the session's clone either way. "" when there is none."""
    common = git_out(directory, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not common:
        # A relative answer is still better than none.
        common = git_out(directory, "rev-parse", "--git-common-dir")
        if common and not os.path.isabs(common):
            common = os.path.join(directory, common)
    toplevel = os.path.normpath(os.path.dirname(common)) if common else ""
    return toplevel if toplevel and os.path.isdir(toplevel) else ""


def title(directory: str) -> str:
    toplevel = main_worktree(directory)
    if not toplevel:
        return ""
    working_copy = os.path.basename(toplevel) or "/"
    # Read the branch from that same main worktree, for the same reason. Detached HEAD gets a short SHA rather than
    # an empty half-title; if even that is unavailable, emit nothing -- a half-title is worse than none.
    branch = git_out(toplevel, "branch", "--show-current") or git_out(toplevel, "rev-parse", "--short", "HEAD")
    if not branch:
        return ""
    agent = hook_common.agent_name()
    # Branches are named <host>/<agent>/<type>/<desc> (older ones carry the working-copy name in the second
    # segment), so the prefix is redundant on a narrow tab. Strip it when it is this session's own -- by agent or
    # by working copy -- leaving <type>/<desc>. Any other branch is left as it is.
    host = hook_common.short_host()
    if host:
        for own in (f"{host}/{agent}/", f"{host}/{working_copy}/"):
            if branch.startswith(own):
                branch = branch[len(own):]
                break
    return f"{agent} {working_copy}/{branch}"


def main() -> int:
    text = title(session_directory(sys.stdin.buffer.read()))
    if text:
        # json.dumps writes the ESC and BEL as \u001b and \u0007; the title's own characters stay UTF-8.
        out = json.dumps({"terminalSequence": f"\x1b]0;{text}\x07"}, ensure_ascii=False)
        sys.stdout.buffer.write(out.encode("utf-8", "surrogateescape") + b"\n")
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
