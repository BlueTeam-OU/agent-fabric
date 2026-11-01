#!/usr/bin/env python3
"""runtime/claude-code/hooks/post-review-shape-guard.py: a PreToolUse hook on Bash.

Refuses a `fabric-pr post-review` that is not the bare command
`fabric-pr post-review [options] <n> [< <report>]`, and names that form.

WHY. Posting the review class's report on one's own pull request is the
author's job (ADR-020), and every account allows it: user-settings.py
writes `Bash(fabric-pr *)` into its permissions. That rule is a prefix
match. A call wrapped in anything else (`cd <worktree> && …`, `… 2>&1 |
tail -8`, an env assignment, a path to the script) does not match it and
goes to the auto-mode classifier, which reads a review posted on the
poster's own pull request as [Self-Approval] and refuses — for the rest of
the session, so the owner had to post by hand: fabric-coordinator on
gateway #75 (2026-10-20) and twice on 2026-10-27, python-dev-03 on #400,
python-dev-01 twice on #449 (2026-11-01, REPLY 01a196fa). A prose allow
entry in policies/auto-mode.json (#396) did not stop it, and a memory did
not reach the other accounts. A deny here costs a rephrase and keeps the
classifier from ever being asked; the classifier's refusal costs the owner.

WHAT COUNTS AS BARE. The whole command, stripped, is `fabric-pr`, then
`post-review`, then words with no shell operator in them — no `;`, `&`,
`|`, `$`, a backtick, a parenthesis, `>` or a newline — and at most one
`<` redirection from a file. Anything else that runs `fabric-pr
post-review` is refused. Quotes are allowed, so is a report path with
spaces in quotes.

WHAT COUNTS AS A POST-REVIEW. `fabric-pr` (or a path ending in it) in a
command position — at the start, or after `;`, `&`, `|`, `(`, `$(`, a
backtick or a newline, past any `VAR=value` words — then `post-review`
after any options. A command that only names the two words (a grep, an
echo) is not one. `bash script.sh` running a post-review is not seen:
this is a fence against the habit of wrapping, not a sandbox.

Output: one deny decision on stdout, or nothing. Exit 0 always: input it
cannot read is passed, never blocked.
"""
from __future__ import annotations

import json
import re
import sys

POST_REVIEW = re.compile(
    r"(?:^|[;&|(`\n]|\$\()\s*"           # a command position
    r"(?:[A-Za-z_]\w*=\S*\s+)*"          # VAR=value words before the command
    r"(?:\S*/)?fabric-pr\s+"             # the script, by name or by path
    r"(?:-\S+(?:\s+[^-\s]\S*)?\s+)*"     # options before the subcommand
    r"post-review\b")
BARE = re.compile(r"fabric-pr\s+post-review(?:\s+[^;&|$`()<>\n]*?)?(?:\s*<\s*[^;&|$`()<>\n]+?)?")
REASON = ("Post the review as the bare command `fabric-pr post-review [--repo <owner/name>] [--model <m>] <n> < <report>`, "
          "and nothing else in the call: no `cd … &&` (use --repo for another repository), no `2>&1`, no pipe, no `;`, "
          "no path to the script, no variable. The bare form is what the `Bash(fabric-pr *)` permission every account "
          "has matches; a wrapped one goes to the auto-mode classifier, which refuses a review on your own pull request "
          "as [Self-Approval] for the rest of the session. Read its output in the next call.")


def refused(cmd: str) -> bool:
    if not POST_REVIEW.search(cmd):
        return False
    return BARE.fullmatch(cmd.strip()) is None


def main() -> int:
    try:
        cmd = json.loads(sys.stdin.read())["tool_input"]["command"]
    except (ValueError, KeyError, TypeError):
        return 0
    if isinstance(cmd, str) and refused(cmd):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": REASON}}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
