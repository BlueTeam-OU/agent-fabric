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
`<` redirection from a file. Quotes are allowed around a word, not around
the command: `"fabric-pr"` and `\\fabric-pr` are not the prefix the rule
matches.

WHAT COUNTS AS RUNNING ONE. Decided on shell words (shlex), not on the
text, because the text misreads both ways (review of #451, F1 and F2): a
quoted string, a commit message, a grep pattern holding the two words is
one word and runs nothing, and `time`, `{ …; }`, `bash -c "…"` run it
though no separator stands before it. `fabric-pr`, by name or path, in a
command position — the start, after a separator (`;` `&` `|` `(` `{` `!`
a backtick, a newline), after a keyword (`then` `do` `if` …) or after a
wrapper (`time` `env` `sudo` `timeout` `nohup` …, past its options and
their arguments) — with `post-review` among its words. The string a
shell's `-c` runs and the words `eval` runs are read the same way. A
heredoc's body is data and is dropped before reading. Not seen, on
purpose: a script file that runs a post-review (`bash post.sh`) and a
`$(…)` inside an unquoted heredoc body; this is a fence against the habit
of wrapping, not a sandbox. A command shlex cannot split (an unclosed
quote) that holds both words is refused unless it is bare: over-reporting
costs a rephrase.

COST. Nothing is split unless both words occur in the text, and shlex is
linear: a 100 000-separator command is read in about 0.3 s, inside the 5 s
the settings give the hook (a quadratic regex took 22 s; F3).

Output: one deny decision on stdout, or nothing. Exit 0 always: input it
cannot read is passed, never blocked.
"""
from __future__ import annotations

import json
import re
import shlex
import sys

BARE = re.compile(r"fabric-pr\s+post-review(?:\s+[^;&|$`()<>\n]*?)?(?:\s*<\s*[^;&|$`()<>\n]+?)?")
HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)(\w+)\1[^\n]*\n.*?\n[ \t]*\2[ \t]*(?=\n|$)", re.DOTALL)
PUNCT = ";&|()<>`\n{}!"
KEYWORDS = {"then", "do", "else", "elif", "if", "while", "until", "time"}
WRAPPERS = {"env", "sudo", "nohup", "nice", "timeout", "stdbuf", "command", "exec", "builtin", "xargs", "ionice", "setsid"}
SHELLS = {"bash", "sh", "dash", "zsh", "ksh"}
REASON = ("Post the review as the bare command `fabric-pr post-review [--repo <owner/name>] [--model <m>] <n> < <report>`, "
          "and nothing else in the call: no `cd … &&` (use --repo for another repository), no `2>&1`, no pipe, no `;`, "
          "no wrapper (time, env, bash -c), no path to the script, no variable. The bare form is what the "
          "`Bash(fabric-pr *)` permission every account has matches; a wrapped one goes to the auto-mode classifier, "
          "which refuses a review on your own pull request as [Self-Approval] for the rest of the session. "
          "Read its output in the next call.")


def words(cmd: str) -> list[str]:
    lx = shlex.shlex(HEREDOC.sub("\n", cmd), posix=True, punctuation_chars=PUNCT)
    lx.whitespace = " \t\r"     # a newline separates commands: it is punctuation here
    lx.whitespace_split = True
    lx.commenters = ""
    return list(lx)


def redirection(word: str) -> bool:
    return bool(word) and set(word) <= set(PUNCT) and ("<" in word or ">" in word)


def separator(word: str) -> bool:
    """`;` `&&` `|` `(` `)` `{` `}` `!` a backtick or a newline, alone or as shlex glued them (`;;`, `|&`, `))`)."""
    return bool(word) and set(word) <= set(PUNCT) and not redirection(word)


def runs_post_review(cmd: str) -> bool:
    """Whether the command runs `fabric-pr post-review`, read on its shell words (the header says how)."""
    w = words(cmd)
    command_position, wrapped, skip_argument = True, False, False
    for i, word in enumerate(w):
        if redirection(word):
            continue                       # its target is the next word, which a command position never reaches
        if separator(word):
            command_position, wrapped, skip_argument = True, False, False
            continue
        if not command_position:
            continue
        name = word.rsplit("/", 1)[-1]
        if wrapped and name != "fabric-pr":
            if word.startswith("-"):
                skip_argument = "=" not in word
                continue
            if skip_argument or "=" in word or re.fullmatch(r"\d+(\.\d+)?[smhd]?", word):
                skip_argument = False
                continue
        if name in KEYWORDS or name in WRAPPERS:
            wrapped, skip_argument = name in WRAPPERS, False
            continue
        if re.fullmatch(r"[A-Za-z_]\w*=.*", word):
            continue                                       # an assignment before the command
        rest = []
        for later in w[i + 1:]:
            if separator(later):
                break
            rest.append(later)
        if name == "fabric-pr" and "post-review" in rest:
            return True
        if name in SHELLS:
            for j, later in enumerate(rest[:-1]):
                if re.fullmatch(r"-\w*c\w*", later):
                    inner = [x for x in rest[j + 1:] if x != "--"]
                    if inner and runs_post_review(inner[0]):
                        return True
                    break
        if name == "eval" and rest and runs_post_review(" ".join(rest)):
            return True
        command_position, wrapped = False, False
    return False


def refused(cmd: str) -> bool:
    if "fabric-pr" not in cmd or "post-review" not in cmd:
        return False
    if BARE.fullmatch(cmd.strip()):
        return False
    try:
        return runs_post_review(cmd)
    except ValueError:
        return True


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
