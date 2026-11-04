#!/usr/bin/env python3
"""runtime/claude-code/hooks/post-review-shape-guard.py: a PreToolUse hook on Bash.

Refuses a command that names `fabric-pr` and `post-review` and is not the
bare command `fabric-pr post-review [options] <n> [< <report>]`, unless
every mention of the two words is in text the shell never runs; and names
the bare form.

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

WHY INERT TEXT, NOT A PARSE OF WHAT RUNS. Two rounds of review on #451
found that deciding which words run misses both ways: a text regex let
`time …`, `{ …; }` and `bash -c "…"` through and denied quoted mentions;
a shlex walk of command positions let `"$(…)"`, `time -p`, `sudo -E bash
-c` and `bash <<EOF` through, and went quadratic and recursive. A guard
for a habit must not need a shell parser to be right (pipe-status-guard
learned the same). So the question is turned round: the two words are
looked for in everything except text the shell provably never runs —
  - a comment (`#` beginning a word, to the end of the line);
  - a single-quoted string, or an ANSI-C `$'…'` one (a `\\'` in it does not
    close it); a quote left open is live, so a misread cannot hide what
    follows (review of #451, F10);
  - the body of a heredoc whose delimiter is quoted (`<<'EOF'`, `<<"EOF"`,
    `<<\\EOF`), wherever it stands, inside a `"$(…)"` included, ended as
    bash ends it: the delimiter alone on its line, leading tabs only after
    `<<-`;
and those two last are live after all when the command names a word that
runs its arguments (RUNNERS: a shell, `eval`, `source`, `su`, `ssh`,
`watch`, `flock`; by name, its quotes off, anywhere) or `.` as a command
word, since a `-c` string, a piped script or a heredoc fed to a shell
runs; `.` as an argument is a path (`grep -rn '…' .`, F9). Everything
else is live: unquoted words,
double-quoted strings (a `$(…)` in one runs), an unquoted heredoc's body.
Over-reported, on purpose, and named in the deny so the session knows the
way through: an unquoted or double-quoted mention (`echo fabric-pr
post-review`, `git commit -m "… fabric-pr post-review …"`) — put the words
in single quotes, a quoted heredoc or a file. Not seen: a script file that
runs a post-review (`bash post.sh`), a command held in a variable and
expanded (`$x`), `$SHELL -c` — a fence against the habit of wrapping, not
a sandbox.

COST. One pass over the text, no recursion and no backtracking: each
character is looked at a bounded number of times, so the 5 s the settings
give the hook covers any command a session sends (review of #451, F3, F6,
F7). Nothing is scanned unless both words occur in the text.

Output: one deny decision on stdout, or nothing. Exit 0 always: input it
cannot read is passed, never blocked.
"""
from __future__ import annotations

import json
import re
import sys

# Greedy over classes that exclude `<`, so a match never backtracks: linear on any input (the lazy form was not).
BARE = re.compile(r"fabric-pr\s+post-review(?:\s[^;&|$`()<>\n]*)?(?:<[^;&|$`()<>\n]*)?")
# A word that runs its arguments as commands, wherever it stands: over-reported in argument position, which costs a
# rephrase. `.` is `source` only as a command word: as an argument it is a path (`grep -rn '…' .`; review of #451, F9).
RUNNERS = {"bash", "sh", "dash", "zsh", "ksh", "eval", "source", "su", "ssh", "watch", "flock"}
WRAPPERS = {"sudo", "env", "exec", "command", "builtin", "nohup", "nice", "time", "timeout", "xargs", "then", "do",
            "else", "if", "while", "until", "!"}
WORD_END = set(" \t\n;&|()<>")
REASON = ("Post the review as the bare command `fabric-pr post-review [--repo <owner/name>] [--model <m>] <n> < <report>`, "
          "and nothing else in the call: no `cd … &&` (use --repo for another repository), no `2>&1`, no pipe, no `;`, "
          "no wrapper (time, env, bash -c), no path to the script, no variable. The bare form is what the "
          "`Bash(fabric-pr *)` permission every account has matches; a wrapped one goes to the auto-mode classifier, "
          "which refuses a review on your own pull request as [Self-Approval] for the rest of the session. "
          "Read its output in the next call. If this command only mentions the two words (a grep, a commit message, "
          "a doc), put them in single quotes, a quoted heredoc (<<'EOF') or a file.")


def live_text(cmd: str) -> str:
    """The text the shell may run: the command less comments, single-quoted strings and quoted-delimiter heredoc
    bodies, those two given back when the command names a shell, eval or source (the header says why)."""
    live: list[str] = []
    inert: list[str] = []
    runner = False
    word: list[str] = []
    stack = ["N"]               # N: unquoted (top level, $( … ) or ` … `); D: inside "…"
    depth = [0]                 # open parentheses inside each $( … )
    pending: list[tuple[str, bool, bool]] = []      # heredocs opened on this line: (delimiter, quoted, <<-)
    first, after_wrapper = True, False      # the next word is a command word; the last command word was a wrapper
    n, i = len(cmd), 0

    def end_word() -> None:
        """Close the word: its quotes are already off (`"bash" -c` names bash), so it is a runner by its name."""
        nonlocal runner, first, after_wrapper
        if word:
            name = "".join(word).rsplit("/", 1)[-1]
            runner = runner or name in RUNNERS or (first and name == ".")
            if first:
                option = after_wrapper and (name.startswith("-") or "=" in name or name.isdigit())
                after_wrapper = name in WRAPPERS or option
                first = after_wrapper or "=" in name     # an assignment leaves the command word still to come
            word.clear()

    def separator() -> None:
        nonlocal first, after_wrapper
        end_word()
        first, after_wrapper = True, False

    while i < n:
        c = cmd[i]
        top = stack[-1]
        if top == "D":
            if c == "\\" and i + 1 < n:
                live.append(cmd[i:i + 2])
                i += 2
                continue
            if c == '"':
                stack.pop()
            elif cmd.startswith("$(", i):
                separator()
                stack.append("S")
                depth.append(0)
                live.append("$(")
                i += 2
                continue
            elif c == "`":
                separator()
                stack.append("B")
            else:
                word.append(c)
            live.append(c)
            i += 1
            continue
        # Unquoted: the top level, a $( … ) or a ` … `.
        if c == "\\" and i + 1 < n:
            live.append(cmd[i:i + 2])
            word.append(cmd[i + 1])
            i += 2
            continue
        if cmd.startswith("$'", i):
            j = i + 2                                    # ANSI-C quoting: \' does not close it (review of #451, F10)
            while j < n and cmd[j] != "'":
                j += 2 if cmd[j] == "\\" else 1
            (inert if j < n else live).append(" " + cmd[i + 2:j] + " ")
            live.append(" ")
            word.append(cmd[i + 2:j])
            i = j + 1
            continue
        if c == "'":
            close = cmd.find("'", i + 1)
            # A quote left open is live: bash refuses the command anyway, and an open quote must not hide what follows.
            (inert if close != -1 else live).append(" " + cmd[i + 1:(n if close == -1 else close)] + " ")
            close = n if close == -1 else close
            live.append(" ")
            word.append(cmd[i + 1:close])
            i = close + 1
            continue
        if c == "#" and not word:
            nl = cmd.find("\n", i)
            i = n if nl == -1 else nl
            continue
        if c == '"':
            stack.append("D")
            live.append(c)
            word.append("")                              # a word has begun: a `#` after it is no comment
            i += 1
            continue
        if cmd.startswith("<<", i) and not cmd.startswith("<<<", i):
            end_word()
            dash = cmd.startswith("<<-", i)
            j = i + 2 + dash
            while j < n and cmd[j] in " \t":
                j += 1
            k = j
            while k < n and cmd[k] not in WORD_END:
                k += 1
            raw = cmd[j:k]
            if raw[:1] in "'\"" and raw[-1:] != raw[:1]:
                close = cmd.find(raw[0], j + 1)          # a quoted delimiter holding a space
                k = n if close == -1 else close + 1
                raw = cmd[j:k]
            delim = raw.replace("'", "").replace('"', "").replace("\\", "")
            if delim:
                pending.append((delim, raw != delim, dash))
            live.append(cmd[i:k])
            i = k
            continue
        if c == "\n" and pending:
            separator()
            live.append(c)
            i += 1
            for delim, quoted, dash in pending:
                body_start = i
                while i < n:
                    nl = cmd.find("\n", i)
                    line_end = n if nl == -1 else nl
                    line = cmd[i:line_end]
                    # bash's own rule: the delimiter alone on its line, leading tabs only after <<- (review of #451, F10).
                    if (line.lstrip("\t") if dash else line) == delim:
                        (inert if quoted else live).append(" " + cmd[body_start:i] + " ")
                        i = line_end
                        break
                    i = line_end + 1
                else:
                    (inert if quoted else live).append(" " + cmd[body_start:n] + " ")
            pending.clear()
            continue
        if top == "S" and c == "(":
            depth[-1] += 1
        elif top == "S" and c == ")":
            if depth[-1] == 0:
                separator()
                stack.pop()
                depth.pop()
                live.append(c)
                i += 1
                continue
            depth[-1] -= 1
        elif top == "B" and c == "`":
            separator()
            stack.pop()
            live.append(c)
            i += 1
            continue
        elif c == "`":
            separator()
            stack.append("B")
            live.append(c)
            i += 1
            continue
        elif cmd.startswith("$(", i):
            separator()
            stack.append("S")
            depth.append(0)
            live.append("$(")
            i += 2
            continue
        if c in ";&|(\n":
            separator()
        elif c in WORD_END:
            end_word()
        else:
            word.append(c)
        live.append(c)
        i += 1
    end_word()
    return "".join(live) + ("".join(inert) if runner else "")


def refused(cmd: str) -> bool:
    if "fabric-pr" not in cmd or "post-review" not in cmd:
        return False
    if BARE.fullmatch(cmd.strip()):
        return False
    text = live_text(cmd)
    at = text.find("fabric-pr")            # a run names the subcommand after the script: `grep post-review bin/fabric-pr` runs none
    return at != -1 and text.find("post-review", at) != -1


def main() -> int:
    try:
        cmd = json.loads(sys.stdin.read())["tool_input"]["command"]
    except (ValueError, KeyError, TypeError):
        return 0
    try:
        deny = isinstance(cmd, str) and refused(cmd)
    except Exception:                       # a guard that cannot decide refuses: over-reporting costs a rephrase
        deny = True
    if deny:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": REASON}}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
