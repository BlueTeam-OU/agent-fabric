#!/usr/bin/env python3
"""runtime/claude-code/hooks/subagent-clone-guard.py — the subagent clone guard (ADR-040 Wave 9 batch 5;
subagent-clone-guard.sh beside it is its forwarder, run by the PreToolUse hook on Write, Edit, MultiEdit,
NotebookEdit and Bash of runtime/claude-code/workspace/settings.json and .claude/settings.json).

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      none read
  stdin     the PreToolUse payload, JSON: agent_id, agent_type, tool_name, cwd, each read as jq's `.f // ""`,
            "" made "-", the four joined by spaces, and the FIRST line of that split by bash's
            `read -r agent_id agent_type tool cwd` (runs of space and tab separate; the last name takes the
            rest, inner spaces kept)
  env       PATH (jq's presence; the `bash` that runs the review fence); the review fence reads its own
  stdout    nothing (allow); one compact deny line; for Bash, the review fence's answer passed through with
            no trailing newline (its own allow-with-updatedInput, or its deny, reworded below)
  stderr    nothing of its own
  exit      0, always: exit 2 would block, and a guard that cannot parse its input allows and says nothing

DECISIONS, in order, with their exact words:
  1. no `jq` on PATH -> ask, the bash's literal line, before stdin is read:
     "The subagent clone guard could not run (jq is not installed). Approve only if this tool call is not a
     subagent writing in the session clone. See CLAUDE.md - Subagents."
     This module needs no jq; the check is kept because the bash's contract (and its oracle) holds it, and it
     fails closed (an ask), main session included, as the bash did. Dropping it is the coordinator's call.
  2. nothing read (stdin not JSON before any value, or every value failed) -> nothing
  3. agent_id "-" or empty (the main session)                         -> nothing
  4. agent_type not exactly one of code-low code-medium code-high code-plan code-review general-purpose
     claude Explore Plan (a fork, a type this control plane does not dispatch) -> nothing
  5. cwd contains "/.claude/worktrees/" (isolated: it may write there) -> nothing
  6. tool Bash: the payload (as `"$(cat)"` held it) is piped to `bash <this directory>/review-bash-guard.sh`;
     for every type but code-review, an answer whose permissionDecision is deny has its reason prefixed with
     WHY + " The read-only fence says: "; the answer is printed as captured, without a trailing newline
  7. tool Write, Edit, MultiEdit or NotebookEdit -> deny:
       code-review: "The review class runs in the session clone and is read-only: it may not use <tool>.
                    Report the finding instead of editing. See CLAUDE.md - Subagents."
       otherwise:   WHY + " It may not use <tool>. See CLAUDE.md - Subagents."
  8. any other tool                                                   -> nothing
  WHY: "This <agent_type> subagent runs in the session clone (<cwd>), not in a worktree of its own, so it is
  read-only here. A subagent resumed by SendMessage runs here: its isolation is not restored. Do not resume a
  writing agent: dispatch a new one with isolation worktree for the next step, or report what you would have
  changed."

The review fence is not rewritten here: review-bash-guard.sh (and the review-bash-guard.py it runs) is called
as the bash called it, so its own fail-closed deny when it cannot run reaches the harness unchanged.

NOT BYTE-IDENTICAL to the bash:
  - a field that is a number or true is joined as Python's JSON renders it, not jq's (jq 1.8 keeps a number's
    literal); an object or array field fails that value, as jq's join does. The harness sends strings.
  - the review fence's answer is re-read and re-written as jq 1.8 would (hook_jq.py); a fence answer that is
    not one JSON object is passed through, as jq's failure left it.
  - a stream of several JSON values, a NaN, a lone surrogate: read as jq 1.8 reads them.

WHY THE GUARD EXISTS, the bash's header kept:

A capability-class subagent running in the SESSION CLONE is read-only. Where a subagent runs is what tells a
writer from a reader. Every writing dispatch carries isolation worktree and works under .claude/worktrees/ — the
dispatch guard (agent-dispatch-guard.sh) refuses one that does not — and the one class that runs unisolated in the
clone is the review class, whose agent file lists no writing tool and fences its Bash (review-bash-guard.sh). That
leaves the dispatches the dispatch guard never sees: an agent() call inside a Workflow script (its tool input is
script text, and both fields default the wrong way — isolation to the clone), and a launch that resolves a class
natively rather than through the Agent tool. This hook is the backstop at the point of the write: a class subagent
whose cwd is not under .claude/worktrees/ may not write, and its Bash gets the review fence (no state-changing git,
no installs, no shell escapes, no redirection into the tree). For the review class it duplicates what the agent
file already says; for everything else it is the only fence. Every unisolated subagent's allowed Bash is
rewritten by the fence to run with a clean environment (no secret inherited, the session markers kept).

SCOPE, deliberately narrow: only when the hook input carries an agent_id (a subagent — the main session is never
touched) AND the agent_type is one this control plane dispatches (the classes, the reviewer, and the harness
built-ins a class-less call would have named). A fork continues the session and may write in the clone by design;
an unknown type is left alone rather than guessed at.

Verified on Claude Code 2.1.270: a subagent's tool call carries agent_id, agent_type and cwd in the hook input,
and a worktree-isolated subagent reports <repo>/.claude/worktrees/agent-<id> as cwd. Whether a Workflow-spawned
agent carries the same fields has not been observed live; the hook allows when they are absent, so it fails open
there, not closed.

Why a writing class is here at all, said in every refusal it gets. Seen live (2026-10-18, a code-low agent
dispatched with isolation worktree): resumed by SendMessage, it ran in the session clone on the session's branch,
its worktree gone; Claude Code does not restore a resumed subagent's isolation. The fence is then right, and the
review fence's own words ("The review class ...") told a code-medium agent nothing (j228). Whether a resumed agent
whose worktree held changes gets it back was not observed.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # `python -I` leaves this directory off
import hook_jq  # noqa: E402

TYPES = ("code-low", "code-medium", "code-high", "code-plan", "code-review", "general-purpose", "claude", "Explore", "Plan")
WRITERS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
FIELDS = ("agent_id", "agent_type", "tool_name", "cwd")
IFS = " \t\n"
NO_JQ = ('{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":'
         '"The subagent clone guard could not run (jq is not installed). Approve only if this tool call is not a subagent '
         'writing in the session clone. See CLAUDE.md - Subagents."}}')


def joined(value) -> list:
    """`[(.agent_id // ""), …] | map(if . == "" then "-" else . end) | join(" ")`."""
    words = []
    for name in FIELDS:
        v = hook_jq.alt(hook_jq.index(value, name), "")
        v = "-" if v == "" else v
        if isinstance(v, (list, dict)):
            raise hook_jq.Failed                  # jq: a string and an object cannot be added
        words.append(v if isinstance(v, str) else hook_jq.raw(v))
    return [" ".join(words)]


def read_r(line: str, names: int) -> list[str]:
    """bash's `read -r a b … z` of one line under the default IFS."""
    rest = line.lstrip(IFS)
    out = []
    for _ in range(names - 1):
        end = 0
        while end < len(rest) and rest[end] not in IFS:
            end += 1
        out.append(rest[:end])
        rest = rest[end:].lstrip(IFS)
    out.append(rest.rstrip(IFS))
    return out


def why(agent_type: str, cwd: str) -> str:
    return (f"This {agent_type} subagent runs in the session clone ({cwd}), not in a worktree of its own, so it is read-only "
            "here. A subagent resumed by SendMessage runs here: its isolation is not restored. Do not resume a writing "
            "agent: dispatch a new one with isolation worktree for the next step, or report what you would have changed.")


def is_deny(value) -> list:
    return [hook_jq.index(hook_jq.index(value, "hookSpecificOutput"), "permissionDecision") == "deny"]


def reworded(text: str, prefix: str) -> str:
    """`jq -c --arg why … '.hookSpecificOutput.permissionDecisionReason |= $why + " The read-only fence says: " + .'`."""
    def each(value):
        if value is not None and not isinstance(value, dict):
            raise hook_jq.Failed
        value = {} if value is None else value
        inner = value.get("hookSpecificOutput")
        if inner is not None and not isinstance(inner, dict):
            raise hook_jq.Failed
        inner = {} if inner is None else inner
        old = inner.get("permissionDecisionReason")
        if old is not None and not isinstance(old, str):
            raise hook_jq.Failed                  # a string and a number cannot be added
        inner["permissionDecisionReason"] = prefix + " The read-only fence says: " + (old or "")
        value["hookSpecificOutput"] = inner
        return [value]
    values, _ = hook_jq.run(text, each)
    return "\n".join(hook_jq.compact(v) for v in values)


def fence(payload: bytes, agent_type: str, cwd: str) -> str:
    try:
        r = subprocess.run(["bash", os.path.join(HERE, "review-bash-guard.sh")], input=payload,
                           stdout=subprocess.PIPE, check=False)
        out = r.stdout
    except OSError:
        out = b""                                 # the bash's `bash` not found: an empty answer, as there
    text = out.replace(b"\0", b"").rstrip(b"\n").decode("utf-8", "replace")
    if agent_type != "code-review":
        verdict, ok = hook_jq.run(text, is_deny)
        if ok and verdict and verdict[-1] is True:
            text = reworded(text, why(agent_type, cwd))
    return text


def main() -> int:
    if shutil.which("jq") is None:
        hook_jq.write(NO_JQ + "\n")
        return 0
    # `input="$(cat)"`: a shell variable holds no NUL and no trailing newline; the fence is given the same bytes.
    payload = sys.stdin.buffer.read().replace(b"\0", b"").rstrip(b"\n")
    values, _ = hook_jq.run(payload.decode("utf-8", "replace"), joined)
    if not values:
        return 0
    agent_id, agent_type, tool, cwd = read_r(values[0].split("\n", 1)[0], 4)
    if agent_id in ("-", ""):
        return 0                                  # the main session, or unparsable
    if agent_type not in TYPES:
        return 0                                  # a fork, or a type this control plane does not dispatch
    if "/.claude/worktrees/" in cwd:
        return 0                                  # isolated: it may write there
    if tool == "Bash":
        hook_jq.write(fence(payload, agent_type, cwd))
    elif tool in WRITERS:
        if agent_type == "code-review":
            reason = (f"The review class runs in the session clone and is read-only: it may not use {tool}. Report the "
                      "finding instead of editing. See CLAUDE.md - Subagents.")
        else:
            reason = f"{why(agent_type, cwd)} It may not use {tool}. See CLAUDE.md - Subagents."
        hook_jq.write(hook_jq.decision("PreToolUse", "deny", reason) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
