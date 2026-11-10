#!/usr/bin/env python3
"""runtime/claude-code/hooks/post-review-shape-guard.py: a PreToolUse hook on Bash.

Refuses a command that names `fabric-pr` and `post-review` and is not the
bare command `fabric-pr post-review [options] <n> [< <report>]` (or its
dispatcher spelling `fabric pr post-review …`), unless every mention of the
two words is in text the shell never runs; and names the bare form.

WHICH WORDS ARE `fabric-pr`. tools/fabric/cli canonical() says, never a
pattern here (agent-fabric ADR-068 §5 rule 7): it reads `fabric-pr`, `fabric
pr`, `bin/fabric-pr` and the `env`/`command` prefixes to the one command, so
a spelling the dispatcher adds is guarded the day it is added. The command
table it reads (runtime/claude-code/commands.json) is from this hook's own
checkout; one that cannot be read refuses, as any other failure to decide.

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

WHAT COUNTS AS BARE. The whole command, stripped, is `fabric-pr` (or
`fabric pr`) as its first word, then `post-review`, then words with no shell
operator in them — no `;`, `&`,
`|`, `$`, a backtick, a parenthesis, `>` or a newline — and at most one
`<` redirection from a file. Quotes are allowed around a word, not around
the command: `"fabric-pr"` and `\\fabric-pr` are not the prefix the rule
matches, and neither is a path, an assignment or `env` before it.

WHY INERT TEXT, NOT A PARSE OF WHAT RUNS. Two rounds of review on #451
found that deciding which words run misses both ways: a text regex let
`time …`, `{ …; }` and `bash -c "…"` through and denied quoted mentions;
a shlex walk of command positions let `"$(…)"`, `time -p`, `sudo -E bash
-c` and `bash <<EOF` through, and went quadratic and recursive. A guard
for a habit must not need a shell parser to be right (pipe-status-guard
learned the same). So the question is turned round: the two words are
looked for in everything except text the shell provably never runs (a
live word canonical() reads as `fabric-pr`, with `post-review` anywhere
after it) —
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
`watch`, `flock`; by bare name, its quotes off, anywhere, and by a path unless
the command only reads files, since `grep … runtime/ssh` reads one) or `.` as a command
word (after `{`, `elif` or a case arm's `)` too) or before `/dev/stdin`,
since a `-c` string, a piped script or a heredoc fed to a shell runs;
`.` as an argument is a path (`grep -rn '…' .`, F9). Everything
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
F7). Nothing is scanned, and no table read, unless `post-review` occurs in the
text: the command's name is not looked for before canonical() is asked.

Output: one deny decision on stdout, or nothing. Exit 0 always: a payload it
cannot read is passed, never blocked (a command table it cannot read is not
a payload: that refuses).
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
# The command and verb this guard is about, compared with what canonical() reads, never with the words as spelled.
COMMAND, VERB = "fabric-pr", "post-review"
# Greedy over classes that exclude `<`, so a match never backtracks: linear on any input (the lazy form was not).
# The command's words come before the `<`; whether they are `fabric-pr post-review` is canonical()'s to say.
BARE = re.compile(r"([^;&|$`()<>\n]*)(?:<[^;&|$`()<>\n]*)?")
# What ends a word of live text for canonical(): the shell's operators and quotes (a double-quoted `"fabric-pr"`
# still runs it) and the backslash (`\fabric-pr` does too).
LIVE_WORD = re.compile(r"[^\s;&|()<>`\"$\\]+")
# canonical() needs at most `fabric <noun> <verb>` to name a command; the arguments are not its question here.
NAMING_WORDS = 3
# A word that runs its arguments as commands, wherever it stands: over-reported in argument position, which costs a
# rephrase. `.` is `source` only as a command word: as an argument it is a path (`grep -rn '…' .`; review of #451, F9).
RUNNERS = {"bash", "sh", "dash", "zsh", "ksh", "eval", "source", "su", "ssh", "watch", "flock"}
WRAPPERS = {"sudo", "env", "exec", "command", "builtin", "nohup", "nice", "time", "timeout", "xargs", "then", "do",
            "else", "elif", "if", "while", "until", "!", "{"}
# What `.` reads a script from when it is fed a heredoc or a pipe, and any /dev/fd/N (`3<<'EOF'`). `.` followed by one of these runs that input,
# wherever the reading of command words placed it: a leading redirection (`2>/dev/null . /dev/stdin`) is a word
# the walk cannot tell from a command (j543, #451 round 4 F11). Over-reported as an argument, which costs a rephrase.
STDIN_PATHS = {"/dev/stdin", "/dev/fd/0", "/proc/self/fd/0"}
# Commands that only read the files they are given: under one of these, a path whose last part names a runner
# (`grep … runtime/ssh`) is a file, not a shell (j543, F12). Anything else keeps a runner by path live, so a command
# word the walk misreads (`2` of `2>/dev/null`, `root` of `sudo -u root`) over-reports instead of letting
# `/bin/bash -c '…'` through (review of #501 round 4, F6). find, sed and awk are not readers: each can run a command.
READERS = {"grep", "egrep", "fgrep", "rg", "ag", "ack", "git", "ls", "cat", "head", "tail", "wc", "diff", "stat",
           "file", "less", "more"}
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
    prev = ""                               # the previous word of this simple command
    command = ""                            # the word the walk took as this simple command's name
    n, i = len(cmd), 0

    def end_word() -> None:
        """Close the word: its quotes are already off (`"bash" -c` names bash), so it is a runner by its name."""
        nonlocal runner, first, after_wrapper, prev, command
        if word:
            full = "".join(word)
            name = full.rsplit("/", 1)[-1]
            # A runner by bare name counts anywhere (`find -exec bash -c '…'` runs it); by path, unless the command
            # only reads files (READERS says why).
            named = name in RUNNERS and ("/" not in full or command not in READERS)
            stdin = full in STDIN_PATHS or (full.startswith("/dev/fd/") and full[8:].isdigit())
            runner = runner or named or (first and name == ".") or (prev == "." and stdin)
            if not (prev == "." and full == "--"):          # `. -- /dev/stdin` reads the path after the --
                prev = full
            if first:
                option = after_wrapper and (name.startswith("-") or "=" in name or name.isdigit())
                after_wrapper = name in WRAPPERS or option
                first = after_wrapper or "=" in name     # an assignment leaves the command word still to come
                if not first:
                    command = name
            word.clear()

    def separator() -> None:
        nonlocal first, after_wrapper, prev, command
        end_word()
        first, after_wrapper, prev, command = True, False, "", ""

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
        if c in ";&|(\n" or (c == ")" and top == "N"):        # `x) cmd`: a case arm's command word follows
            separator()
        elif c in WORD_END:
            end_word()
        else:
            word.append(c)
        live.append(c)
        i += 1
    end_word()
    return "".join(live) + ("".join(inert) if runner else "")


def canonical_module():
    """tools/fabric/cli/canonical.py, its package loaded BY PATH as fabric_cli (as tools/fabric/cli/fabric.py loads
    it), so nothing on sys.path answers for the import."""
    if "fabric_cli" not in sys.modules:
        here = os.path.join(ROOT, "tools", "fabric", "cli")
        spec = importlib.util.spec_from_file_location("fabric_cli", os.path.join(here, "__init__.py"),
                                                      submodule_search_locations=[here])
        if spec is None or spec.loader is None:
            raise ImportError(f"no package at {here}")
        package = importlib.util.module_from_spec(spec)
        sys.modules["fabric_cli"] = package
        spec.loader.exec_module(package)
    return importlib.import_module("fabric_cli.canonical")


def bare(cmd: str, canonical) -> bool:
    """The words before the one `<` are the post-review itself, its command word first: not a prefix canonical()
    reads through (`env`, `LC_ALL=C`), not a path, not quoted — none of those is what `Bash(fabric-pr *)` (or
    `Bash(fabric pr *)`) matches."""
    shape = BARE.fullmatch(cmd)
    words = shape.group(1).split() if shape else []
    read = canonical.canonical(words) if words else None
    return (read is not None and read[0] == COMMAND and read[1][:1] == [VERB]
            and words[0] in (COMMAND, canonical.DISPATCHER))


def refused(cmd: str) -> bool:
    if VERB not in cmd:
        return False
    canonical = canonical_module()
    if bare(cmd.strip(), canonical):
        return False
    text = live_text(cmd)
    last = text.rfind(VERB)                 # a run names the subcommand after the script: `grep post-review bin/fabric-pr` runs none
    if last == -1:
        return False
    words = LIVE_WORD.findall(text, 0, last)
    # Every live word before the last `post-review` is asked whether it starts `fabric-pr`: a text walk, not a parse of
    # command positions (the header says why), so `echo fabric-pr post-review` is over-reported as it always was. By
    # its last part, so a path outside a `bin` (`./fabric-pr`, `/opt/x/fabric-pr`) stays the script it always was here.
    return any((read := canonical.canonical([os.path.basename(words[k]), *words[k + 1:k + NAMING_WORDS]])) is not None
               and read[0] == COMMAND for k in range(len(words)))


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
